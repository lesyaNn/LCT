import styles from './state-illustration.module.css';

export type StateIllustrationKind = 'empty' | 'error' | '403' | '404' | '500';

interface StateIllustrationProps {
  kind: StateIllustrationKind;
  compact?: boolean;
  className?: string;
}

function SceneBase({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <>
      <path className={styles.surface} d="M40 186c0-58 48-106 108-106 26 0 50 9 69 24 14-26 42-44 75-44 47 0 85 37 85 82 0 8-1 15-3 22 28 8 49 33 49 63H40v-41Z" />
      <circle className={styles.brandSoft} cx="332" cy="69" r="24" />
      <circle className={styles.orangeSoft} cx="86" cy="91" r="15" />
      <path className={styles.lineSoft} d="M49 228h368" />
      {children}
    </>
  );
}

function EmptyScene() {
  return (
    <SceneBase>
      <path className={styles.paper} d="M137 84h159c10 0 18 8 18 18v105H119V102c0-10 8-18 18-18Z" />
      <path className={styles.line} d="M137 84h159c10 0 18 8 18 18v105H119V102c0-10 8-18 18-18Z" />
      <path className={styles.brandSoft} d="M151 116h132v57H151z" />
      <path className={styles.brandLine} d="M161 143h112M161 158h76" />
      <path className={styles.orange} d="M103 181h80l14 26h40l14-26h80l-17 46H120l-17-46Z" />
      <path className={styles.line} d="M103 181h80l14 26h40l14-26h80l-17 46H120l-17-46Z" />
      <circle className={styles.brand} cx="343" cy="164" r="15" />
      <path className={styles.paper} d="M337 164h12M343 158v12" />
    </SceneBase>
  );
}

function ErrorScene() {
  return (
    <SceneBase>
      <rect className={styles.paper} x="112" y="88" width="210" height="133" rx="18" />
      <rect className={styles.line} x="112" y="88" width="210" height="133" rx="18" />
      <path className={styles.brandSoft} d="M112 121h210v100H112z" />
      <circle className={styles.orange} cx="139" cy="105" r="6" />
      <circle className={styles.brand} cx="160" cy="105" r="6" />
      <path className={styles.line} d="m171 183 31-31 25 25 38-47" />
      <path className={styles.orangeLine} d="m254 130 12-1-1 12" />
      <path className={styles.line} d="M176 219v18M258 219v18M154 237h126" />
      <path className={styles.paper} d="M319 169a34 34 0 1 1 0 68 34 34 0 0 1 0-68Z" />
      <path className={styles.line} d="M319 183v24M319 219h.1" />
    </SceneBase>
  );
}

function ForbiddenScene() {
  return (
    <SceneBase>
      <rect className={styles.paper} x="128" y="116" width="178" height="111" rx="20" />
      <rect className={styles.line} x="128" y="116" width="178" height="111" rx="20" />
      <path className={styles.brandSoft} d="M166 116V91c0-29 23-52 51-52s51 23 51 52v25h-27V91c0-14-11-25-24-25s-24 11-24 25v25h-27Z" />
      <path className={styles.brandLine} d="M166 116V91c0-29 23-52 51-52s51 23 51 52v25" />
      <circle className={styles.orange} cx="217" cy="165" r="15" />
      <path className={styles.orangeLine} d="M217 177v20" />
      <path className={styles.lineSoft} d="M102 142H73M361 142h-29M92 184H62M371 184h-29" />
    </SceneBase>
  );
}

function NotFoundScene() {
  return (
    <SceneBase>
      <path className={styles.brandSoft} d="M121 89h166v119H121z" />
      <path className={styles.line} d="M121 208V89h166v119" />
      <path className={styles.brand} d="M149 115h111v18H149z" />
      <path className={styles.orange} d="M149 151h75v18h-75z" />
      <path className={styles.lineSoft} d="M204 133v69" />
      <circle className={styles.paper} cx="304" cy="171" r="42" />
      <circle className={styles.brandLine} cx="304" cy="171" r="42" />
      <path className={styles.brandLine} d="m334 201 34 34" />
      <path className={styles.line} d="M276 171h56M304 143v56" />
      <path className={styles.orangeLine} d="m82 163 20-20M102 163l-20-20" />
    </SceneBase>
  );
}

function ServerScene() {
  return (
    <SceneBase>
      <rect className={styles.paper} x="119" y="73" width="198" height="152" rx="18" />
      <rect className={styles.line} x="119" y="73" width="198" height="152" rx="18" />
      <path className={styles.brandSoft} d="M141 100h154v43H141zM141 155h154v43H141z" />
      <circle className={styles.brand} cx="164" cy="121" r="7" />
      <circle className={styles.orange} cx="164" cy="176" r="7" />
      <path className={styles.lineSoft} d="M188 121h83M188 176h83" />
      <path className={styles.orange} d="m324 117 18 10 18-10 12 20-18 11v21l18 10-12 21-18-11-18 11-12-21 18-10v-21l-18-11 12-20Z" />
      <circle className={styles.paper} cx="342" cy="158" r="15" />
      <path className={styles.line} d="M342 148v20M332 158h20" />
      <path className={styles.line} d="M173 225v13M263 225v13M151 238h134" />
    </SceneBase>
  );
}

export function StateIllustration({ kind, compact = false, className = '' }: StateIllustrationProps) {
  const scene = kind === 'empty'
    ? <EmptyScene />
    : kind === '403'
      ? <ForbiddenScene />
      : kind === '404'
        ? <NotFoundScene />
        : kind === '500'
          ? <ServerScene />
          : <ErrorScene />;

  return (
    <svg
      aria-hidden="true"
      className={`${styles.illustration} ${compact ? styles.compact : ''} ${className}`}
      focusable="false"
      viewBox="0 0 460 270"
    >
      {scene}
    </svg>
  );
}
