/**
 * The brand mark: four cells on the violet accent, rotated slightly, with the
 * opacity stepping down and back up so it reads as a mark rather than a grid.
 *
 * The prototype's mark is a four-square gradient block. No icon glyph matches
 * it, and approximating it with a chart icon would lose the only piece of brand
 * imagery the product has, so it is built from spans.
 */
export function LogoMark({
  size = 27,
  className = "",
}: {
  size?: number;
  className?: string;
}) {
  const cells = ["", "opacity-70", "opacity-50", "opacity-85"];
  return (
    <span
      aria-hidden="true"
      className={`grid -rotate-6 shrink-0 grid-cols-2 gap-0.5 rounded-lg bg-primary-600 p-[5px] shadow-[0_6px_18px_rgba(108,75,244,0.4)] ${className}`}
      style={{ width: size, height: size }}
    >
      {cells.map((tone, index) => (
        <span key={index} className={`rounded-[1.5px] bg-white ${tone}`} />
      ))}
    </span>
  );
}

/** The mark beside the wordmark, for the sidebar and the login panel. */
export function Logo({ className = "" }: { className?: string }) {
  return (
    <span className={`flex items-center gap-2.5 ${className}`}>
      <LogoMark />
      <span className="font-display text-[20px] font-bold leading-none tracking-[-0.5px] text-white">
        StatFlow
      </span>
    </span>
  );
}

export default Logo;