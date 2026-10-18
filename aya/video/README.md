# AYA narrated Remotion demo

A 94-second, 1920×1080, 30fps film built with Remotion 4.0.536. It uses actual AYA application captures, animated evidence diagrams, measured results, and local macOS Samantha narration. The model calls, tests, GitHub result and training receipt predate the recording; no new model inference is simulated in the film.

## Rebuild

Install the exact dependencies in package.json. Regenerate narration with macOS say from story.json if changed, or use the checked-in WAV assets. Run `npm run render`. This renders the base composition and its closing sequence into `.build/`, then runs the preserved FFmpeg recipe in `render-final.sh` to normalize narration, overlay the recorded-live timing label, and produce the final master. `npm run finalize` repeats only that final encode from existing intermediate files. The macOS recipe requires FFmpeg with VideoToolbox and Arial; set `AYA_NODE`, `AYA_FFMPEG`, and `AYA_CHROME` to override executable paths. Regenerating on other hardware may produce a different file hash while preserving the same content. The current workstation reuses a local dependency installation through an ignored node_modules symlink; that symlink is not part of the package.

Source: src/movie.tsx. Narration and scene durations: story.json. Actual captures and audio: public/. Output: output/AYA-demo.mp4. Subtitles: captions.srt, copied to output/AYA-demo.srt by the renderer.

## Evidence

- Recovered SQL component: https://github.com/Ali-Maq/crusoe-developer-hub/pull/2
- Factory: https://github.com/Ali-Maq/aya/pull/1
- MASS integration: https://github.com/Ali-Maq/mass/pull/1
- Public run: https://github.com/Ali-Maq/aya/tree/a751e3dbab6ee545309ded5b5d9bb013fac03cfe/aya/demo/evidence/mass-public-sql/db5f5b51190a4b97
- Current SFT job: ftjob-3f54c5ea7cee4dbcb1819004d2c1d7a9, succeeded, 26,624 trained tokens.
- Checkpoint: ftmodel-2ac55e69-6a3c-4b2d-a3d1-0fd93bf5455a, not deployed or evaluated.

The public baseline scored 12/12 development; native v0 and v1 each 11/12. The retained v0 passed 3/6 held-out; baseline held-out was not measured. No accuracy gain is claimed. Selection used independently verified baseline outputs, 10 training / 2 validation / 0 held-out, for final-answer SFT; this is not the full paper's trajectory training or a recursive tuned-model cycle. Usage is measured whole-episode calls/tokens, not dollar costs or learned budget optimization.

Native Hermes uses fresh workspaces in a shared OpenShell worker. Cross-run filesystem isolation is not enforced. Generated SQL runs in separate restricted containers. This source/runtime SQL demo does not claim binary decompilation. Public dataset familiarity may limit interpretation.

## Delivered master

94 seconds; H.264 1920×1080 at 30 fps, AAC stereo 48 kHz, 73,014,201 bytes. SHA256: `a12b6be9aba422698cc4fe6a9e592df327e7de0b9c30da4e6a8f5ec41c8d5bdb`. Scene frames and complete audio decoding were inspected. The video is the measured experiment demo; the accompanying deck distinguishes the target product vision from actual results in its appendix.
