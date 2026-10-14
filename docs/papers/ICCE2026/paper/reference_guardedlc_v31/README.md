# GuardedLC Overleaf v31

Main file: `main.tex`.

This package is an Overleaf-ready IEEEtran source bundle. The bundled `main.pdf` was compiled from this source and remains within the six-page conference limit.

v31 revision summary:
- Broadens Related Work with the three reviewer-suggested references on mobile-network performance, AI segmentation, and secure voice processing, while clearly marking them as complementary system context rather than direct GuardedLC baselines.
- Adds a concise runtime implementation description following the actual GuardedLC pipeline in Fig. 1.
- Strengthens the generalizability limitations: all evaluated commands are author-generated text, with no independent user corpus, ASR errors, or in-cabin interaction.
- Restores native IEEEtran caption handling so table titles are rendered in IEEE small caps, and shortens table captions to title form.
- Preserves first-appearance numeric citation order and the conservative, coverage-bounded safety claims.

Compile with:

```bash
pdflatex main.tex
pdflatex main.tex
```
