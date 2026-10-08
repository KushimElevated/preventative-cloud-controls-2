'use client';
export default function ErrorPage({ reset }: { reset: () => void }) {
  return <main className="login"><h1>The workspace could not render.</h1><p>Reload the workspace to recover. No approval or cloud deployment was performed by this error page.</p><button className="button" onClick={reset}>Retry workspace</button></main>;
}
