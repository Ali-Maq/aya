import React from "react";
import {
  AbsoluteFill,
  Audio,
  Composition,
  Img,
  Sequence,
  interpolate,
  staticFile,
  useCurrentFrame,
} from "remotion";
import story from "../story.json";

const FPS = 30;
const C = {
  paper: "#F4F2EB",
  ink: "#12221F",
  green: "#08785B",
  mint: "#BCF5D1",
  muted: "#899B92",
  red: "#B95547",
  line: "#31463F",
};
const font = "Arial, sans-serif";
const duration = story.reduce((n, s) => n + s.seconds * FPS, 0);
function fade(f: number, start = 0, length = 18) {
  return interpolate(f, [start, start + length], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
}
function rise(f: number, delay = 0) {
  return {
    opacity: fade(f, delay),
    transform: `translateY(${interpolate(f, [delay, delay + 24], [36, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })}px)`,
  };
}
function Eyebrow({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        fontSize: 22,
        letterSpacing: 4,
        textTransform: "uppercase",
        color: C.green,
        fontWeight: 700,
        marginBottom: 26,
      }}
    >
      {children}
    </div>
  );
}
function Title({
  children,
  size = 74,
}: {
  children: React.ReactNode;
  size?: number;
}) {
  return (
    <div
      style={{
        fontSize: size,
        lineHeight: 1.04,
        fontWeight: 700,
        letterSpacing: -2.5,
      }}
    >
      {children}
    </div>
  );
}
function Screenshot({
  src,
  x,
  y,
  w,
  h,
  frame,
  pan = 0,
}: {
  src: string;
  x: number;
  y: number;
  w: number;
  h: number;
  frame: number;
  pan?: number;
}) {
  return (
    <div
      style={{
        position: "absolute",
        left: x,
        top: y,
        width: w,
        height: h,
        overflow: "hidden",
        borderRadius: 14,
        background: "white",
        boxShadow: "0 30px 80px #071b2225",
        border: "1px solid #D4D8D0",
      }}
    >
      <Img
        src={staticFile(src)}
        style={{
          width: "100%",
          transform: `translateY(${interpolate(frame, [0, 300], [0, pan], { extrapolateRight: "clamp" })}px) scale(${interpolate(frame, [0, 300], [1, 1.025], { extrapolateRight: "clamp" })})`,
          transformOrigin: "top center",
        }}
      />
    </div>
  );
}
function Foot({
  children,
  dark = false,
}: {
  children: React.ReactNode;
  dark?: boolean;
}) {
  return (
    <div
      style={{
        position: "absolute",
        left: 90,
        bottom: 42,
        right: 90,
        fontSize: 23,
        color: dark ? "#B5C8BD" : "#52665B",
      }}
    >
      {children}
    </div>
  );
}
function Problem() {
  const f = useCurrentFrame();
  return (
    <AbsoluteFill style={{ background: C.ink, color: C.paper, padding: 90 }}>
      <div style={{ fontSize: 32, letterSpacing: 8, color: C.mint }}>AYA</div>
      <div style={{ marginTop: 120, ...rise(f, 10) }}>
        <Title size={100}>
          Software is cheaper
          <br />
          to generate.
        </Title>
      </div>
      <div
        style={{ fontSize: 62, marginTop: 54, color: C.mint, ...rise(f, 90) }}
      >
        Does the feature actually fit?
      </div>
      <div style={{ display: "flex", gap: 66, marginTop: 80, fontSize: 30 }}>
        {[
          "Existing behavior",
          "Your product contract",
          "Independent tests",
        ].map((s, i) => (
          <span
            key={s}
            style={{
              ...rise(f, 155 + i * 20),
              borderTop: "2px solid #587367",
              paddingTop: 20,
            }}
          >
            {s}
          </span>
        ))}
      </div>
      <Foot dark>
        Reference behavior → tested component → reviewable delivery
      </Foot>
    </AbsoluteFill>
  );
}
function Request() {
  const f = useCurrentFrame();
  return (
    <AbsoluteFill style={{ padding: 90, background: C.paper, color: C.ink }}>
      <div style={{ width: 710, ...rise(f) }}>
        <Eyebrow>01 · Define the feature</Eyebrow>
        <Title>
          Your repository.
          <br />A real reference.
        </Title>
        <p style={{ fontSize: 34, lineHeight: 1.4, marginTop: 50 }}>
          “Bring Fireworks’ SQL tools
          <br />
          to the Crusoe cookbook.”
        </p>
        <div style={{ fontSize: 25, color: "#52665B", marginTop: 50 }}>
          Target: Ali-Maq/crusoe-developer-hub
          <br />
          <br />
          Reference: fw-ai/cookbook
          <br />
          <br />
          Contract: reviewed and frozen
        </div>
      </div>
      <Screenshot
        src="recover.png"
        x={850}
        y={85}
        w={980}
        h={900}
        frame={f}
        pan={-50}
      />
      <div
        style={{
          position: "absolute",
          left: interpolate(f, [100, 170], [1600, 1000], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          }),
          top: interpolate(f, [100, 170], [810, 590], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          }),
          opacity: fade(f, 95),
          fontSize: 55,
          textShadow: "0 2px 5px #fff",
        }}
      >
        ↖
      </div>
      <Foot>Actual AYA interface · Onyx frontend · GitHub feature request</Foot>
    </AbsoluteFill>
  );
}
function Investigate() {
  const f = useCurrentFrame();
  const nodes = [
    "Pinned reference",
    "REA investigation",
    "Hermes + OpenShell",
    "Candidate module",
  ];
  return (
    <AbsoluteFill style={{ background: C.ink, color: C.paper, padding: 90 }}>
      <Eyebrow>02 · Inspect before implementing</Eyebrow>
      <Title>
        Behavior becomes an
        <br />
        executable contract.
      </Title>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          marginTop: 100,
          opacity: 1 - fade(f, 155, 20),
        }}
      >
        {nodes.map((n, i) => (
          <React.Fragment key={n}>
            <div
              style={{
                ...rise(f, 20 + i * 35),
                width: 365,
                borderTop: `3px solid ${C.mint}`,
                paddingTop: 30,
                fontSize: 36,
                lineHeight: 1.3,
              }}
            >
              <div style={{ fontSize: 22, color: C.mint, marginBottom: 22 }}>
                0{i + 1}
              </div>
              {n}
            </div>
            {i < 3 && (
              <span
                style={{
                  fontSize: 42,
                  color: C.mint,
                  padding: "0 27px",
                  opacity: fade(f, 50 + i * 35),
                }}
              >
                →
              </span>
            )}
          </React.Fragment>
        ))}
      </div>
      <div
        style={{
          marginTop: 105,
          fontFamily: "Menlo, monospace",
          fontSize: 24,
          lineHeight: 1.8,
          color: "#BDD9CA",
          opacity: fade(f, 165),
        }}
      >
        <span style={{ color: C.mint }}>reference</span> fw-ai/cookbook @
        6ada4081
        <br />
        <span style={{ color: C.mint }}>inspect</span> sql_tools.py · source +
        runtime capture
        <br />
        <span style={{ color: C.mint }}>worker</span> native Hermes · Crusoe
        DeepSeek-V4-Pro
      </div>
      <div style={{ opacity: fade(f, 165) }}>
        <Screenshot
          src="rea.png"
          x={970}
          y={350}
          w={860}
          h={620}
          frame={f}
          pan={-120}
        />
      </div>
      <Foot dark>
        Fresh workspaces share one OpenShell worker. SQL runs in separate
        restricted containers.
      </Foot>
    </AbsoluteFill>
  );
}
function Repair() {
  const f = useCurrentFrame();
  const accepted = f > 125;
  return (
    <AbsoluteFill style={{ background: C.paper, color: C.ink, padding: 90 }}>
      <Eyebrow>03 · Independent acceptance</Eyebrow>
      <Title>A failing case blocks delivery.</Title>
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          gap: 30,
          marginTop: 80,
        }}
      >
        <span
          style={{
            fontSize: 210,
            fontWeight: 700,
            letterSpacing: -10,
            color: accepted ? C.green : C.red,
          }}
        >
          {accepted ? "118" : "117"}
        </span>
        <span style={{ fontSize: 100, color: "#85958C" }}>/ 118</span>
        <div
          style={{
            marginLeft: 85,
            fontSize: 46,
            lineHeight: 1.3,
            ...rise(f, 140),
          }}
        >
          Repair accepted.
          <br />
          Fresh evaluation passed.
        </div>
      </div>
      <div
        style={{
          marginTop: 55,
          padding: "30px 0",
          borderTop: "1px solid #C6D0C6",
          borderBottom: "1px solid #C6D0C6",
          fontFamily: "Menlo, monospace",
          fontSize: 31,
        }}
      >
        <span style={{ color: C.red }}>query = " "</span>
        <span style={{ margin: "0 45px" }}>→</span>
        <span>{accepted ? "invalid_request ✓" : "contract mismatch"}</span>
      </div>
      <Foot>
        Recorded SQL recovery run 492e2ca7851347f5 · development + fresh-seed
        checks
      </Foot>
    </AbsoluteFill>
  );
}
function Deliver() {
  const f = useCurrentFrame();
  return (
    <AbsoluteFill style={{ background: C.paper, color: C.ink, padding: 90 }}>
      <div style={{ width: 690 }}>
        <Eyebrow>04 · Ship a working component</Eyebrow>
        <Title>
          A real PR.
          <br />A live product.
        </Title>
        <div
          style={{
            marginTop: 60,
            fontFamily: "Menlo, monospace",
            fontSize: 27,
            lineHeight: 1.8,
            ...rise(f, 25),
          }}
        >
          GitHub PR #2
          <br />
          Add verified Crusoe
          <br />
          repository analyst cookbook
          <br />
          <br />
          <span style={{ color: C.green }}>
            ✓ CI: SUCCESS
            <br />✓ 54 target tests
            <br />✓ 4 real Crusoe questions
          </span>
        </div>
        <div style={{ fontSize: 24, marginTop: 44, color: "#52665B" }}>
          Fresh GitHub data.
          <br />
          Actual model SQL and result rows.
        </div>
      </div>
      <Screenshot
        src={
          f < 85
            ? "live-before.png"
            : f < 165
              ? "live-running.png"
              : "live-after.png"
        }
        x={850}
        y={90}
        w={980}
        h={900}
        frame={f}
        pan={-20}
      />
      <div
        style={{
          position: "absolute",
          left: 1675,
          top: 460,
          fontSize: 58,
          color: C.ink,
          opacity: f > 45 && f < 110 ? 1 : 0,
          transform: `translateY(${interpolate(f, [45, 80], [80, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })}px)`,
        }}
      >
        ↖
      </div>
      <Foot>
        github.com/Ali-Maq/crusoe-developer-hub/pull/2 · Recorded live · timing
        condensed
      </Foot>
    </AbsoluteFill>
  );
}
function Mass() {
  const f = useCurrentFrame();
  const rows = [
    ["Bare baseline", "12 / 12", 1, 4544],
    ["Initial Hermes", "11 / 12", 8, 48451],
    ["MASS candidate", "11 / 12", 22, 68667],
  ];
  return (
    <AbsoluteFill style={{ background: C.ink, color: C.paper, padding: 90 }}>
      <Eyebrow>05 · Test changes to the agent</Eyebrow>
      <Title size={68}>MASS proposed. The evaluator decided.</Title>
      <div style={{ fontSize: 26, color: "#B5C8BD", marginTop: 24 }}>
        Public Spider subset · 12 development questions · real databases
      </div>
      <div style={{ marginTop: 55 }}>
        {rows.map((r, i) => (
          <div
            key={String(r[0])}
            style={{
              display: "grid",
              gridTemplateColumns: "400px 220px 1fr 200px",
              alignItems: "center",
              gap: 30,
              height: 105,
              borderBottom: "1px solid #344F43",
              ...rise(f, 30 + i * 30),
            }}
          >
            <div style={{ fontSize: 36 }}>{r[0]}</div>
            <div style={{ fontSize: 44, color: i === 0 ? C.mint : C.paper }}>
              {r[1]}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
              <div
                style={{
                  height: 28,
                  width: interpolate(
                    f,
                    [65 + i * 30, 130 + i * 30],
                    [0, Number(r[2]) * 18],
                    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
                  ),
                  background: i === 0 ? C.mint : "#8DA59A",
                  borderRadius: 3,
                }}
              />
              <span style={{ fontSize: 27, whiteSpace: "nowrap" }}>
                {r[2]} {r[2] === 1 ? "call" : "calls"}
              </span>
            </div>
            <div style={{ fontSize: 27, textAlign: "right" }}>
              {Number(r[3]).toLocaleString()} tokens
            </div>
          </div>
        ))}
      </div>
      <div style={{ marginTop: 65, ...rise(f, 225) }}>
        <span style={{ fontSize: 61, fontWeight: 700 }}>
          Retained v0: 3 / 6 held out
        </span>
        <div style={{ fontSize: 28, color: "#B5C8BD", marginTop: 20 }}>
          No accuracy gain. Baseline held-out performance was not evaluated.
        </div>
      </div>
      <Foot dark>
        Actual upstream RHI · v0/v1 tie retains v0 · Public data may be familiar
        to the model
      </Foot>
    </AbsoluteFill>
  );
}
function Selection() {
  const f = useCurrentFrame();
  return (
    <AbsoluteFill style={{ background: C.paper, color: C.ink, padding: 90 }}>
      <div style={{ width: 760 }}>
        <Eyebrow>06 · Learn from verified evidence</Eyebrow>
        <Title size={70}>
          Correct answers.
          <br />
          Measured effort.
        </Title>
        <div
          style={{
            fontSize: 90,
            fontWeight: 700,
            color: C.green,
            marginTop: 42,
            ...rise(f, 35),
          }}
        >
          1 call{" "}
          <span style={{ fontSize: 36, fontWeight: 400, color: "#52665B" }}>
            vs 22
          </span>
        </div>
        <div style={{ fontSize: 29, lineHeight: 1.4, marginTop: 15 }}>
          Baseline selected on development.
          <br />
          12 verified answers from Langfuse.
        </div>
        <div
          style={{ display: "flex", gap: 70, marginTop: 55, ...rise(f, 95) }}
        >
          <div>
            <strong style={{ fontSize: 75 }}>10</strong>
            <div style={{ fontSize: 26 }}>training</div>
          </div>
          <div>
            <strong style={{ fontSize: 75 }}>2</strong>
            <div style={{ fontSize: 26 }}>validation</div>
          </div>
          <div>
            <strong style={{ fontSize: 75 }}>0</strong>
            <div style={{ fontSize: 26 }}>held-out</div>
          </div>
        </div>
        <div
          style={{
            fontSize: 32,
            color: C.green,
            marginTop: 50,
            ...rise(f, 175),
          }}
        >
          Crusoe SFT succeeded · Qwen3.5-9B
        </div>
      </div>
      <Screenshot
        src="training.png"
        x={900}
        y={80}
        w={930}
        h={920}
        frame={f}
        pan={-25}
      />
      <Foot>
        Final-answer distillation. No winning MASS teacher; tuned quality and
        serving remain unverified.
      </Foot>
    </AbsoluteFill>
  );
}
function Close() {
  const f = useCurrentFrame();
  return (
    <AbsoluteFill style={{ background: C.ink, color: C.paper, padding: 90 }}>
      <div
        style={{
          fontSize: 140,
          fontWeight: 700,
          letterSpacing: -7,
          ...rise(f),
        }}
      >
        AYA
      </div>
      <div style={{ marginTop: 65, ...rise(f, 25) }}>
        <Title size={83}>
          Recover software.
          <br />
          Measure agent changes.
        </Title>
      </div>
      <div
        style={{ marginTop: 65, fontSize: 35, color: C.mint, ...rise(f, 75) }}
      >
        MASS: workflow search → verified training
        <br />
        <span style={{ color: "#B5C8BD" }}>
          Next gate: serving + evaluation → next cycle
        </span>
      </div>
      <div style={{ fontSize: 30, marginTop: 75, ...rise(f, 135) }}>
        github.com/Ali-Maq/aya
      </div>
      <Foot dark>
        Real calls. Recorded evidence. No demonstrated accuracy improvement or
        tuned-model deployment.
      </Foot>
    </AbsoluteFill>
  );
}
const scenes = {
  problem: Problem,
  request: Request,
  investigate: Investigate,
  repair: Repair,
  deliver: Deliver,
  mass: Mass,
  selection: Selection,
  close: Close,
};
function Film() {
  const f = useCurrentFrame();
  let start = 0;
  return (
    <AbsoluteFill style={{ fontFamily: font }}>
      {story.map((s, index) => {
        const from = start;
        start += s.seconds * FPS;
        const Scene = scenes[s.id as keyof typeof scenes];
        return (
          <Sequence key={s.id} from={from} durationInFrames={s.seconds * FPS}>
            <Scene />
            <Audio src={staticFile(`voice-${index}.wav`)} />
            <div
              style={{
                position: "absolute",
                bottom: 0,
                left: 0,
                width: "100%",
                height: 6,
                background: "#13392A",
              }}
            >
              <div
                style={{
                  height: "100%",
                  background: C.mint,
                  width: `${(f / duration) * 100}%`,
                }}
              />
            </div>
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
}
export function Root() {
  return (
    <Composition
      id="AYA"
      component={Film}
      durationInFrames={duration}
      fps={FPS}
      width={1920}
      height={1080}
    />
  );
}
