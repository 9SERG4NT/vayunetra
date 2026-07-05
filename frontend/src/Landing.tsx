// The marketing landing page is a fully self-contained static document
// (frontend/public/landing.html) with its own compiled Tailwind + WebGL shader.
// We render it in a full-viewport iframe so its stylesheet can't collide with the
// app's Tailwind, and its "Launch the Product" CTAs (target="_top" href="/app")
// break out of the frame into the React dashboard.
export default function Landing() {
  return (
    <iframe
      title="VayuNetra — Urban Air Quality Intelligence"
      src="/landing.html"
      className="h-full w-full border-0"
    />
  );
}
