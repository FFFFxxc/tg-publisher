const lines = [
  "M-80 571C216 623 417 604 588 458S842 160 1092 161s301 125 440 32",
  "M-80 615C208 673 441 647 624 506S852 212 1107 213s293 111 423 20",
  "M-80 655C223 713 467 696 652 556S877 261 1128 270s274 98 406 13",
  "M-80 701C219 757 494 739 683 601S903 307 1161 323s242 92 365 0",
  "M-80 750C232 795 514 785 709 650S950 356 1187 372s231 79 347 -8",
];

export default function HomeSignal() {
  return <div className="home-signal" aria-hidden="true">
    <svg viewBox="0 0 1440 820" preserveAspectRatio="xMaxYMin slice" focusable="false">
      <defs>
        <radialGradient id="publisher-signal-haze" cx="72%" cy="24%" r="65%">
          <stop offset="0" stopColor="#f4defe" stopOpacity=".82" />
          <stop offset=".58" stopColor="#d0a6e7" stopOpacity=".46" />
          <stop offset="1" stopColor="#c199de" stopOpacity="0" />
        </radialGradient>
        <linearGradient id="publisher-signal-ink" x1="0" x2="1">
          <stop offset="0" stopColor="#825a9f" stopOpacity="0" />
          <stop offset=".4" stopColor="#825a9f" stopOpacity=".45" />
          <stop offset=".8" stopColor="#744b99" stopOpacity=".64" />
          <stop offset="1" stopColor="#744b99" stopOpacity=".28" />
        </linearGradient>
        <pattern id="publisher-signal-grid" width="28" height="28" patternUnits="userSpaceOnUse">
          <circle cx="3" cy="3" r="1.1" fill="#604473" opacity=".33" />
        </pattern>
        <radialGradient id="publisher-signal-grid-fade" cx="86%" cy="19%" r="58%">
          <stop offset="0" stopColor="white" />
          <stop offset="1" stopColor="white" stopOpacity="0" />
        </radialGradient>
        <mask id="publisher-signal-grid-mask">
          <rect width="1440" height="820" fill="url(#publisher-signal-grid-fade)" />
        </mask>
      </defs>
      <rect className="home-signal-haze" x="280" y="-80" width="1230" height="830" fill="url(#publisher-signal-haze)" />
      <rect width="1440" height="820" fill="url(#publisher-signal-grid)" mask="url(#publisher-signal-grid-mask)" />
      <g className="home-signal-traces" fill="none">
        {lines.map(d => <path key={d} d={d} stroke="url(#publisher-signal-ink)" strokeWidth="1.15" />)}
        <path className="home-signal-pulse" d={lines[0]} pathLength="100" />
        <path className="home-signal-pulse home-signal-pulse-secondary" d={lines[2]} pathLength="100" />
        <path className="home-signal-pulse home-signal-pulse-tertiary" d={lines[4]} pathLength="100" />
      </g>
    </svg>
  </div>;
}
