import { Canvas, useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";

export type AgentNode = { id: string; number: number; name: string; availability?: string };

function cssColor(name: string, fallback: string) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v ? `rgb(${v.split(/\s+/).join(",")})` : fallback;
}

export function webglAvailable() {
  try {
    const c = document.createElement("canvas");
    return !!(c.getContext("webgl2") || c.getContext("webgl"));
  } catch {
    return false;
  }
}

export function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  useEffect(() => {
    const m = window.matchMedia("(prefers-reduced-motion: reduce)");
    const on = () => setReduced(m.matches);
    m.addEventListener("change", on);
    return () => m.removeEventListener("change", on);
  }, []);
  return reduced;
}

/** Pipeline agents (1-9) sit on an inner ring in execution order; assurance services (10-12) on an outer arc. */
export function layout(agents: AgentNode[]) {
  const pipeline = agents.filter((a) => a.number <= 9).sort((a, b) => a.number - b.number);
  const assurance = agents.filter((a) => a.number > 9).sort((a, b) => a.number - b.number);
  const pos: Record<string, [number, number, number]> = {};
  pipeline.forEach((a, i) => {
    const t = (i / pipeline.length) * Math.PI * 2 - Math.PI / 2;
    pos[a.id] = [Math.cos(t) * 2.6, Math.sin(t) * 2.6, Math.sin(t * 2) * 0.35];
  });
  assurance.forEach((a, i) => {
    const t = Math.PI * 0.15 + (i / Math.max(1, assurance.length - 1)) * Math.PI * 0.7;
    pos[a.id] = [Math.cos(t) * 3.9, -Math.sin(t) * 3.9 * 0.55 - 0.4, -1.1];
  });
  return { pipeline, assurance, pos };
}

function Core({ animate }: { animate: boolean }) {
  const ref = useRef<THREE.Group>(null);
  const cyan = useMemo(() => cssColor("--cyan", "#45C6DB"), []);
  const violet = useMemo(() => cssColor("--violet", "#9A8CF5"), []);
  useFrame((_, dt) => {
    if (animate && ref.current) { ref.current.rotation.y += dt * 0.15; ref.current.rotation.x += dt * 0.04; }
  });
  return (
    <group ref={ref}>
      <mesh><icosahedronGeometry args={[1.05, 1]} /><meshBasicMaterial color={cyan} wireframe transparent opacity={0.55} /></mesh>
      <mesh><sphereGeometry args={[0.62, 32, 32]} /><meshStandardMaterial color={violet} emissive={violet} emissiveIntensity={0.35} roughness={0.4} /></mesh>
    </group>
  );
}

function Documents({ count, animate }: { count: number; animate: boolean }) {
  const ref = useRef<THREE.Points>(null);
  const n = count <= 0 ? 0 : Math.min(420, Math.round(Math.log10(count + 1) * 90));
  const geo = useMemo(() => {
    const g = new THREE.BufferGeometry();
    const arr = new Float32Array(n * 3);
    let seed = 7;
    const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
    for (let i = 0; i < n; i++) {
      const u = rnd() * 2 - 1, th = rnd() * Math.PI * 2, r = 4.6 + rnd() * 1.6;
      const s = Math.sqrt(1 - u * u);
      arr.set([r * s * Math.cos(th), r * u * 0.6, r * s * Math.sin(th) - 1], i * 3);
    }
    g.setAttribute("position", new THREE.BufferAttribute(arr, 3));
    return g;
  }, [n]);
  useFrame((_, dt) => { if (animate && ref.current) ref.current.rotation.y -= dt * 0.03; });
  if (n === 0) return null;
  return <points ref={ref} geometry={geo}><pointsMaterial size={0.045} color={cssColor("--muted", "#8C97AB")} transparent opacity={0.7} /></points>;
}

function Path({ points, color, opacity = 0.45 }: { points: THREE.Vector3[]; color: string; opacity?: number }) {
  const line = useMemo(() => {
    const g = new THREE.BufferGeometry().setFromPoints(points);
    return new THREE.Line(g, new THREE.LineBasicMaterial({ color, transparent: true, opacity }));
  }, [points, color, opacity]);
  return <primitive object={line} />;
}

function Pulse({ curve, offset }: { curve: THREE.CatmullRomCurve3; offset: number }) {
  const ref = useRef<THREE.Mesh>(null);
  useFrame(({ clock }) => {
    if (ref.current) ref.current.position.copy(curve.getPointAt((clock.getElapsedTime() * 0.08 + offset) % 1));
  });
  return <mesh ref={ref}><sphereGeometry args={[0.06, 12, 12]} /><meshBasicMaterial color={cssColor("--cyan", "#45C6DB")} /></mesh>;
}

function availabilityColor(a?: string) {
  if (a === "available") return cssColor("--cyan", "#45C6DB");
  if (a === "partial") return cssColor("--amber", "#E0B25A");
  if (a === "unavailable") return cssColor("--danger", "#EF7D7D");
  return cssColor("--muted", "#8C97AB");
}

function Nodes({ agents, selected, onSelect, interactive }: { agents: AgentNode[]; selected?: string; onSelect?: (id: string) => void; interactive: boolean }) {
  const { pipeline, pos } = useMemo(() => layout(agents), [agents]);
  const [hover, setHover] = useState<string | null>(null);
  const ring = useMemo(() => pipeline.map((a) => new THREE.Vector3(...pos[a.id])), [pipeline, pos]);
  return (
    <group>
      {ring.length > 1 && <Path points={ring} color={cssColor("--line", "#263043")} opacity={0.9} />}
      {agents.filter((a) => a.number > 9).map((a) => (
        <Path key={`l-${a.id}`} points={[new THREE.Vector3(0, 0, 0), new THREE.Vector3(...pos[a.id])]} color={cssColor("--violet", "#9A8CF5")} opacity={0.25} />
      ))}
      {agents.map((a) => {
        const active = selected === a.id || hover === a.id;
        return (
          <mesh
            key={a.id}
            position={pos[a.id]}
            scale={active ? 1.35 : 1}
            onClick={interactive ? (e) => { e.stopPropagation(); onSelect?.(a.id); } : undefined}
            onPointerOver={interactive ? (e) => { e.stopPropagation(); setHover(a.id); document.body.style.cursor = "pointer"; } : undefined}
            onPointerOut={interactive ? () => { setHover(null); document.body.style.cursor = ""; } : undefined}
          >
            {a.number > 9 ? <octahedronGeometry args={[0.2, 0]} /> : <sphereGeometry args={[0.2, 24, 24]} />}
            <meshStandardMaterial color={availabilityColor(a.availability)} emissive={availabilityColor(a.availability)} emissiveIntensity={active ? 0.9 : 0.35} />
          </mesh>
        );
      })}
    </group>
  );
}

export function AgentScene({ agents, documents = 0, running = false, selected, onSelect, interactive = false, height = 420 }: {
  agents: AgentNode[]; documents?: number; running?: boolean; selected?: string; onSelect?: (id: string) => void; interactive?: boolean; height?: number;
}) {
  const reduced = usePrefersReducedMotion();
  const [gl] = useState(webglAvailable);
  const { pipeline, pos } = useMemo(() => layout(agents), [agents]);
  const curve = useMemo(() => {
    const pts = pipeline.map((a) => new THREE.Vector3(...pos[a.id]));
    return pts.length > 1 ? new THREE.CatmullRomCurve3(pts, false) : null;
  }, [pipeline, pos]);
  if (!gl) return <StaticAgentMap agents={agents} selected={selected} onSelect={onSelect} height={height} />;
  const animate = !reduced;
  return (
    <div style={{ height }} className="relative w-full" role="img" aria-label="Three-dimensional map of the agent pipeline. Node colours show service availability.">
      <Canvas camera={{ position: [0, 0.6, 8.2], fov: 50 }} dpr={[1, 1.75]} frameloop={animate || interactive ? "always" : "demand"}>
        <ambientLight intensity={0.5} />
        <pointLight position={[4, 5, 6]} intensity={40} />
        <CameraDrift enabled={animate} />
        <Core animate={animate} />
        <Documents count={documents} animate={animate} />
        <Nodes agents={agents} selected={selected} onSelect={onSelect} interactive={interactive} />
        {running && animate && curve && [0, 0.33, 0.66].map((o) => <Pulse key={o} curve={curve} offset={o} />)}
      </Canvas>
    </div>
  );
}

function CameraDrift({ enabled }: { enabled: boolean }) {
  useFrame(({ camera, clock, pointer }) => {
    if (!enabled) return;
    const t = clock.getElapsedTime();
    camera.position.x += (pointer.x * 0.8 + Math.sin(t * 0.1) * 0.3 - camera.position.x) * 0.03;
    camera.position.y += (0.6 + pointer.y * 0.4 - camera.position.y) * 0.03;
    camera.lookAt(0, 0, 0);
  });
  return null;
}

/** Static fallback for devices without WebGL: same layout projected to 2D. */
export function StaticAgentMap({ agents, selected, onSelect, height = 420 }: { agents: AgentNode[]; selected?: string; onSelect?: (id: string) => void; height?: number }) {
  const { pipeline, pos } = layout(agents);
  const P = (id: string) => [200 + pos[id][0] * 40, 170 - pos[id][1] * 40] as const;
  return (
    <svg viewBox="0 0 400 340" style={{ height }} className="w-full" role="img" aria-label="Agent pipeline map">
      <polyline fill="none" stroke="rgb(var(--line))" strokeWidth="1.5" points={pipeline.map((a) => P(a.id).join(",")).join(" ")} />
      <circle cx="200" cy="170" r="22" fill="rgb(var(--violet) / 0.5)" stroke="rgb(var(--cyan))" />
      {agents.map((a) => {
        const [x, y] = P(a.id);
        return (
          <g key={a.id} onClick={() => onSelect?.(a.id)} className={onSelect ? "cursor-pointer" : ""}>
            <circle cx={x} cy={y} r={selected === a.id ? 11 : 8} fill={availabilityColor(a.availability)} />
            <text x={x} y={y + 3.5} textAnchor="middle" fontSize="8" fill="rgb(var(--base))">{a.number}</text>
          </g>
        );
      })}
    </svg>
  );
}
