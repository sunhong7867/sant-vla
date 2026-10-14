"""Ground-truth world pose of a Gazebo model via the gz CLI.

`/odom` is DiffDrive wheel-integrated (drifts, ignores manual drags). Bridging
`/world/default/pose/info` loses entity names in this ros_gz version. So we read
the model's true world pose directly with `gz model -m <name> -p` and parse it.
"""

import collections
import math
import os
import re
import signal
import shutil
import subprocess
import threading
import time


def _topic_echo_cmd(gz_bin, topic):
    """argv that echoes a gz topic. Prefer the gz-transport-topic helper itself
    over the `gz topic` ruby wrapper: one process instead of two, and nothing
    left behind when the reader dies (2026-10-02)."""
    import glob
    for cand in sorted(glob.glob("/opt/ros/*/opt/gz_transport_vendor/libexec/gz/transport*/gz-transport-topic")) + \
            sorted(glob.glob("/usr/libexec/gz/transport*/gz-transport-topic")):
        if os.access(cand, os.X_OK):
            return [cand, "-e", "-t", topic]
    return [gz_bin, "topic", "-e", "-t", topic]


def _die_with_parent():
    # Linux: SIGTERM this child when the reader process dies, even by SIGKILL
    try:
        import ctypes
        ctypes.CDLL("libc.so.6", use_errno=True).prctl(1, signal.SIGTERM)  # PR_SET_PDEATHSIG
    except Exception:
        pass


def resolve_gz_bin(explicit=""):
    return explicit or shutil.which("gz") or "/opt/ros/jazzy/opt/gz_tools_vendor/bin/gz"


def query_world_pose(gz_bin, model, timeout=6.0, tries=2):
    """Retrying wrapper: the ruby `gz` CLI slowed past 3 s late in long runs
    (2026-10-04 goto collection: reset_failed 0 -> 84 % per 100 eps over 19 h)."""
    for _ in range(tries):
        r = _query_world_pose_once(gz_bin, model, timeout)
        if r is not None:
            return r
    return None


def _query_world_pose_once(gz_bin, model, timeout):
    """Return (x, y, yaw) of `model` in the world frame, or None on failure.

    Parses `gz model -m <model> -p`, whose output contains an XYZ bracket and an
    RPY bracket, e.g.:
        - Pose [ XYZ (m) ] [ RPY (rad) ]:
          [3.700000 24.594300 0.012650]
          [-0.000000 0.000000 -1.570740]
    """
    try:
        out = subprocess.run(
            [gz_bin, "model", "-m", model, "-p"],
            capture_output=True, text=True, timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    triples = []
    for grp in re.findall(r"\[([^\]]+)\]", out.stdout):
        parts = grp.replace(",", " ").split()
        try:
            vals = [float(x) for x in parts]
        except ValueError:
            continue  # skip non-numeric brackets like "[ XYZ (m) ]"
        if len(vals) == 3:
            triples.append(vals)
    if len(triples) >= 2:
        x, y, _ = triples[0]
        yaw = triples[1][2]
        return (x, y, yaw)
    return None


class WorldPoseStream:
    """High-rate ground-truth pose by streaming `gz topic -e` and parsing the
    model's pose blocks. Much faster than repeated `gz model -p` CLI calls
    (which cost ~150ms each).

    Source (2026-10-02): the model's own PosePublisher topic
    ``/model/<model>/pose`` when it exists (the ego prius carries one), else
    the world ``dynamic_pose/info`` dump. The dump holds every moving entity,
    so each reader's ruby burnt a core parsing it, and it skipped 0.3-1.4 s
    at a time during collection. Both topics print the same ``name:`` /
    ``position`` / ``orientation`` text, so one parser serves both. If the
    model topic stays silent for ``fallback_s`` the stream switches to the
    dump for good."""

    def __init__(self, gz_bin, model, world="default", fallback_s=4.0):
        self.gz_bin = gz_bin
        self.model = model
        self.world_topic = f"/world/{world}/dynamic_pose/info"
        self.topic = f"/model/{model}/pose"
        self.fallback_s = fallback_s
        self.latest = None  # (x, y, yaw)
        # sim time of `latest` from the message header (None if absent) —
        # stamping on receipt instead puts the reader's own lag into the time
        self.latest_t = None
        # Every parsed sample with its header stamp, for readers that need the
        # full stream. The helper's stdout is block-buffered into a pipe, so
        # samples arrive in bursts of ~10; a reader polling `latest` kept only
        # the last of each burst — 15 Hz with 0.4-0.6 s holes out of a 50 Hz
        # topic (tripilot, 2026-10-02). Bounded: nobody draining costs nothing.
        self.samples = collections.deque(maxlen=4000)
        self.received_at = 0.0
        # Monotonic counter, bumped on every parsed sample. A poller can compare
        # it to detect a genuinely new reading; polling `latest` alone cannot
        # tell a fresh value from a repeat, and recording repeats as distinct
        # timestamped samples corrupts any downstream interpolation.
        self.seq = 0
        self._run = True
        self._proc = None

    def start(self):
        threading.Thread(target=self._loop, daemon=True).start()
        threading.Thread(target=self._watch_fallback, daemon=True).start()
        return self

    def drain(self):
        """Pop and return all stamped samples received since the last call."""
        out = []
        while True:
            try:
                out.append(self.samples.popleft())
            except IndexError:
                return out

    def _kill_proc(self):
        # `gz topic -e` is a ruby wrapper around gz-transport-topic; killing
        # only the wrapper orphaned the child, which kept parsing the world
        # dump forever (four found under systemd on 2026-10-02). The reader
        # runs in its own session, so the whole group goes.
        proc = self._proc
        if proc is None:
            return
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except Exception:
            try:
                proc.terminate()
            except Exception:
                pass

    def _watch_fallback(self):
        # Readers often start before the sim (or the ego) is up, so silence
        # alone is not evidence that the model topic is missing. Fall back
        # only once the ego exists in the world and still has no pose topic.
        while self._run and self.seq == 0 and self.topic != self.world_topic:
            time.sleep(self.fallback_s)
            if self.seq != 0:
                return
            try:
                out = subprocess.run([self.gz_bin, "topic", "-l"], capture_output=True,
                                     text=True, timeout=5.0).stdout
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
            if self.topic in out.split():
                continue                       # publisher there, data coming
            if self.model in list_models(self.gz_bin):
                self.topic = self.world_topic  # ego without PosePublisher
                self._kill_proc()              # _loop restarts on the dump
                return

    def stop(self):
        self._run = False
        self._kill_proc()

    def _loop(self):
        while self._run:
            try:
                self._proc = subprocess.Popen(
                    _topic_echo_cmd(self.gz_bin, self.topic),
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    text=True, bufsize=1, start_new_session=True,
                    preexec_fn=_die_with_parent,
                )
            except FileNotFoundError:
                return
            cur = None
            mode = None
            px = py = oz = ow = None
            hsec = hnsec = None
            for line in self._proc.stdout:
                if not self._run:
                    break
                s = line.strip()
                if cur is None and s.startswith("sec:"):
                    try:
                        hsec, hnsec = int(s[4:]), 0
                    except ValueError:
                        pass
                    continue
                if cur is None and s.startswith("nsec:"):
                    try:
                        hnsec = int(s[5:])
                    except ValueError:
                        pass
                    continue
                if s.startswith("name:"):
                    cur = s.split('"')[1] if '"' in s else None
                    mode = None
                    px = py = oz = ow = 0.0
                    continue
                if cur != self.model:
                    continue
                if s.startswith("position"):
                    mode = "pos"
                    continue
                if s.startswith("orientation"):
                    mode = "ori"
                    continue
                try:
                    if mode == "pos" and s.startswith("x:"):
                        px = float(s[2:])
                    elif mode == "pos" and s.startswith("y:"):
                        py = float(s[2:])
                    elif mode == "ori" and s.startswith("z:"):
                        oz = float(s[2:])
                    elif mode == "ori" and s.startswith("w:"):
                        ow = float(s[2:])
                except ValueError:
                    pass
                # Protobuf text omits zero-valued coordinates/quaternion
                # components. A complete orientation block is a sample even
                # at x=0, y=0 or a cardinal heading.
                if mode == "ori" and s == "}":
                    yaw = math.atan2(2.0 * ow * oz, 1.0 - 2.0 * oz * oz)
                    self.latest = (px, py, yaw)
                    self.latest_t = (hsec + hnsec * 1e-9) if hsec is not None else None
                    if self.latest_t is not None:
                        self.samples.append((self.latest_t, px, py, yaw))
                    self.received_at = time.monotonic()
                    self.seq += 1
                    cur = None
                    mode = None
                    px = py = oz = ow = None
            time.sleep(0.2)  # stream ended; brief pause before restart


def list_models(gz_bin, timeout=4.0):
    """Return all model names in the running world via `gz model --list`."""
    try:
        out = subprocess.run([gz_bin, "model", "--list"],
                             capture_output=True, text=True, timeout=timeout)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    names, grab = [], False
    for line in out.stdout.splitlines():
        s = line.strip()
        if s.lower().startswith("available models"):
            grab = True
            continue
        if grab and s.startswith("- "):
            names.append(s[2:].strip())
    return names
