import os
from glob import glob

from setuptools import find_packages, setup

package_name = 'sant_vla_pkg'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'config'), glob('config/*.yaml')),
        # Nodes read these from the source tree so edits take effect without a
        # rebuild; the installed copy is what the real-car deployment ships.
        (os.path.join('share', package_name, 'config'), glob('config/*.json')),
        (os.path.join('share', package_name, 'config'), glob('config/*.config')),
    ],
    install_requires=['setuptools', 'pyyaml'],
    zip_safe=True,
    maintainer='sunhong',
    maintainer_email='skku.boot2@gmail.com',
    description='VLA navigation research: zone mapping, oracle navigator, data engine, and evaluation for SANT-VLA.',
    license='GPL-3',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'route_oracle_node = sant_vla_pkg.route_oracle_node:main',
            'vla_bridge_node = sant_vla_pkg.vla_bridge_node:main',
            'episode_recorder_node = sant_vla_pkg.episode_recorder_node:main',
            'gz_reset = sant_vla_pkg.gz_reset:main',
            'zone_capture_gui_node = sant_vla_pkg.zone_capture_gui_node:main',
            'track_roi_editor_node = sant_vla_pkg.track_roi_editor_node:main',
            'navigator_node = sant_vla_pkg.navigator_node:main',
            'chat_gui_node = sant_vla_pkg.chat_gui_node:main',
            'alpamayo_teacher_server = sant_vla_pkg.alpamayo_teacher_server:main',
            'alpamayo_real_server = sant_vla_pkg.alpamayo_real_server:main',
            'data_engine_node = sant_vla_pkg.data_engine_node:main',
            'action_sentence_generator = sant_vla_pkg.action_sentence_generator:main',
            'action_policy_node = sant_vla_pkg.action_policy_node:main',
            'zone_sequence_test_node = sant_vla_pkg.zone_sequence_test_node:main',
            'policy_node = sant_vla_pkg.policy_node:main',
            'obstacle_monitor_node = sant_vla_pkg.obstacle_monitor_node:main',
            'obstacle_data_collector_node = sant_vla_pkg.obstacle_data_collector_node:main',
            'obstacle_vla_node = sant_vla_pkg.obstacle_vla_node:main',
            'car_teleop_node = sant_vla_pkg.car_teleop_node:main',
        ],
    },
)
