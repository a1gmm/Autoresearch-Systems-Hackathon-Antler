export default function Home() {
  return (
    <main className="min-h-screen bg-slate-950 text-slate-100">
      <section className="mx-auto grid max-w-7xl gap-4 p-4 lg:grid-cols-[320px_minmax(0,1fr)_320px]">
        <div className="rounded border border-slate-800 bg-slate-900 p-4">Project input</div>
        <div className="rounded border border-slate-800 bg-slate-900 p-4">Research graph and trace</div>
        <div className="rounded border border-slate-800 bg-slate-900 p-4">Verification summary</div>
        <div className="rounded border border-slate-800 bg-slate-900 p-4 lg:col-span-3">Applicability matrix</div>
      </section>
    </main>
  );
}
