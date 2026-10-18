#!/usr/bin/env bash
# Rebuild the 94-second narrated master; no API or model calls are made.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p .build output
NODE_BIN="${AYA_NODE:-node}"
FFMPEG_BIN="${AYA_FFMPEG:-ffmpeg}"
CHROME_BIN="${AYA_CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
CLI=node_modules/@remotion/cli/remotion-cli.js
if [[ "${1:-}" != "--finalize-only" ]]; then
  "$NODE_BIN" "$CLI" render src/index.ts AYA .build/AYA-demo-render.mp4 --codec h264 --crf 18 --concurrency 4 --browser-executable "$CHROME_BIN"
  "$NODE_BIN" "$CLI" render src/index.ts AYA .build/close-final.mp4 --frames 2460-2819 --codec h264 --crf 18 --concurrency 2 --browser-executable "$CHROME_BIN"
fi
# The master replaces the closing audio and normalizes narration. The header
# identifies the condensed before/pending/after sequence as recorded live.
"$FFMPEG_BIN" -y -hide_banner -loglevel warning \
  -i .build/AYA-demo-render.mp4 -i .build/close-final.mp4 -i public/voice-7.wav \
  -filter_complex "[0:v]trim=end=82,setpts=PTS-STARTPTS[v0];[1:v]trim=end=12,setpts=PTS-STARTPTS[v1];[v0][v1]concat=n=2:v=1:a=0,drawtext=fontfile='/System/Library/Fonts/Supplemental/Arial.ttf':text='Recorded live · timing condensed':fontsize=26:fontcolor=0x12221F:x=850:y=48:enable='between(t,43,55)'[v];[0:a]atrim=end=82,asetpts=PTS-STARTPTS[a0];[2:a]apad=whole_dur=12,atrim=end=12,asetpts=PTS-STARTPTS[a1];[a0][a1]concat=n=2:v=0:a=1,loudnorm=I=-16:TP=-1.5:LRA=11[a]" \
  -map '[v]' -map '[a]' -c:v h264_videotoolbox -b:v 8M -pix_fmt yuv420p \
  -c:a aac -b:a 192k -ar 48000 -movflags +faststart -t 94 output/AYA-demo.mp4
cp captions.srt output/AYA-demo.srt
ffprobe -v error -show_entries stream=codec_name,width,height,r_frame_rate,sample_rate,channels -show_entries format=duration,size -of json output/AYA-demo.mp4 > .build/video-probe.json
