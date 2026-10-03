interface ScoreRingProps {
  /** 0-100. Values outside the range are clamped so the conic gradient can't invert. */
  score: number;
  /** Rendered under the score, e.g. "Excellent". */
  caption?: string;
  size?: number;
}

/**
 * The prototype's score dial: a conic-gradient ring with an opaque inner disc,
 * so the arc is drawn by the gradient and the centre is punched out with a plain
 * background rather than a mask (cheaper, and it inherits the panel colour).
 *
 * The track colour is deliberately a pale tint of the accent rather than a grey:
 * a grey ring next to a coloured arc reads as "disabled", which mislabels a
 * score that simply isn't full yet.
 */
export function ScoreRing({
  score,
  caption,
  size = 80,
}: ScoreRingProps) {
  const clamped = Math.min(100, Math.max(0, score));
  const angle = Math.round(clamped * 3.6);

  return (
    <div
      className="relative grid shrink-0 place-items-center rounded-full"
      style={{
        width: size,
        height: size,
        padding: 7,
        background: `conic-gradient(#6C4BF4 0deg ${angle}deg, #EFEAF6 ${angle}deg 360deg)`,
      }}
      role="img"
      aria-label={`${caption ?? "Score"}: ${clamped} out of 100`}
    >
      <div className="absolute inset-[7px] rounded-full bg-surface-panel" />
      <div className="relative flex items-baseline gap-0.5">
        <strong className="font-display text-[21px] font-bold tracking-[-0.02em] text-ink">
          {Math.round(clamped)}
        </strong>
        <span className="text-[11px] text-ink-muted">/100</span>
      </div>
    </div>
  );
}

export default ScoreRing;