export type TimelineShot = {
  id: string;
  time: string;
  duration?: number;
  start?: number;
  start_ms?: number;
};

export type ShotTimelineAction<T extends TimelineShot> =
  | { type: "update"; index: number; changes: Partial<T> }
  | { type: "insert"; index: number; shot: T }
  | { type: "delete"; index: number }
  | { type: "reorder"; dragId: string; targetId: string };

export function recomputeShotStarts<T extends TimelineShot>(cards: T[]): T[] {
  let cursor = 0;
  return cards.map((card) => {
    const duration = Number(card.duration ?? 3);
    const updated = {
      ...card,
      start: Number(cursor.toFixed(3)),
      start_ms: Math.round(cursor * 1000),
      duration,
      time: `${cursor.toFixed(1)}–${(cursor + duration).toFixed(1)}s`,
    };
    cursor += duration;
    return updated;
  });
}

export function reduceShotTimeline<T extends TimelineShot>(
  cards: T[],
  action: ShotTimelineAction<T>,
): T[] {
  const next = [...cards];
  if (action.type === "update") {
    if (!next[action.index]) return cards;
    next[action.index] = { ...next[action.index], ...action.changes };
  } else if (action.type === "insert") {
    next.splice(action.index, 0, action.shot);
  } else if (action.type === "delete") {
    if (next.length <= 1 || !next[action.index]) return cards;
    const [removed] = next.splice(action.index, 1);
    const receiver = Math.min(action.index, next.length - 1);
    next[receiver] = {
      ...next[receiver],
      duration: Number(next[receiver].duration ?? 3) + Number(removed.duration ?? 3),
    };
  } else {
    const from = next.findIndex((shot) => shot.id === action.dragId);
    const to = next.findIndex((shot) => shot.id === action.targetId);
    if (from < 0 || to < 0 || from === to) return cards;
    const [moved] = next.splice(from, 1);
    next.splice(to, 0, moved);
  }
  return recomputeShotStarts(next);
}
