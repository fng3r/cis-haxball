// Translate native physics names once at the boundary. No inherited metrics.
const color = value => value < 0 ? 'transparent' : value.toString(16).padStart(6, '0');
const point = value => [value.x, value.y];
function physics(disc) {
  return { radius: disc.Z, invMass: disc.aa, damping: disc.Ca, bCoef: disc.m,
    gravity: point(disc.oa), cMask: disc.h ?? null, cGroup: disc.v ?? null };
}
export function readStadium(st) {
  return {
    name: st.w, width: st.$b, height: st.qc,
    bg: { type: ['none', 'grass', 'hockey'][st.ld] || 'none', width: st.Td, height: st.Sd,
      kickOffRadius: st.kd, cornerRadius: st.Uc, color: color(st.jd) },
    goals: st.tc.map(goal => ({ p0: point(goal.W), p1: point(goal.ca), team: goal.qe.$ === 1 ? 'red' : 'blue' })),
    vertexes: st.J.map(vertex => ({ x: vertex.a.x, y: vertex.a.y, bCoef: vertex.m, cMask: vertex.h, cGroup: vertex.v })),
    segments: st.U.map(segment => ({ v0: st.J.indexOf(segment.W), v1: st.J.indexOf(segment.ca),
      curve: segment.Co(), bias: segment.Cc || 0,
      color: color(segment.R), vis: segment.Za, cMask: segment.h, cGroup: segment.v, bCoef: segment.m })),
    planes: st.qa.map(plane => ({ normal: point(plane.wa), dist: plane.Ua, cMask: plane.h, cGroup: plane.v, bCoef: plane.m })),
    discs: st.F.slice(1).map(disc => ({ ...physics(disc), pos: point(disc.a), speed: point(disc.D), color: color(disc.R) })),
    ballPhysics: st.F[0] ? physics(st.F[0]) : null,
    playerPhysics: { ...physics(st.ge), acceleration: st.ge.Ce, kickingAcceleration: st.ge.Te,
      kickingDamping: st.ge.Ue, kickStrength: st.ge.Re, kickback: st.ge.Se },
    joints: st.pb.map(joint => ({ d0: joint.Yd, d1: joint.Zd, length: [joint.Hb, joint.ec], strength: Number.isFinite(joint.ne) ? joint.ne : 'rigid' })),
  };
}
