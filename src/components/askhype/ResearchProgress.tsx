import { useEffect, useState } from 'react';
import { listResearch, researchFailureMessage } from '../../services/chat-api';
import type { ResearchJob } from '../../types/chat';

// The shell and progress component share this research-specific polling module.
// oxlint-disable-next-line react/only-export-components
export function useResearchJobs(conversationId: string | null, token: string | undefined, revision: number) {
  const [snapshot, setSnapshot] = useState<{ key: string; jobs: ResearchJob[]; offline: boolean }>();
  const [retry, setRetry] = useState(0);
  const key = JSON.stringify([conversationId, token, revision, retry]);
  useEffect(() => {
    if (!conversationId || !token) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    let failures = 0;
    let jobs: ResearchJob[] = [];
    const poll = async () => {
      try {
        jobs = await listResearch(conversationId, {
          accessToken: token, signal: AbortSignal.any([controller.signal, AbortSignal.timeout(15_000)]),
        });
        if (controller.signal.aborted) return;
        failures = 0;
        setSnapshot({ key, jobs, offline: false });
        if (jobs.some((job) => job.status === 'queued' || job.status === 'running')) {
          timer = setTimeout(poll, 10_000);
        }
      } catch {
        if (controller.signal.aborted) return;
        failures += 1;
        setSnapshot({ key, jobs, offline: true });
        if (failures < 5) timer = setTimeout(poll, Math.min(5_000 * 2 ** (failures - 1), 30_000));
      }
    };
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [conversationId, token, key]);
  return {
    jobs: snapshot?.key === key ? snapshot.jobs : undefined,
    offline: snapshot?.key === key && snapshot.offline,
    retry: () => setRetry((value) => value + 1),
  };
}

export function ResearchProgress({ job }: { job: ResearchJob }) {
  const [now, setNow] = useState(Date.now);
  const active = job.status === 'queued' || job.status === 'running';
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [active]);
  const seconds = Math.max(0, Math.floor(((active ? now : Date.parse(job.updated_at)) - Date.parse(job.created_at)) / 1000));
  const elapsed = [Math.floor(seconds / 60), seconds % 60].map((part) => String(part).padStart(2, '0')).join(':');
  return (
    <section className="my-3 rounded-lg border border-chat-border bg-chat-surface p-4 break-words">
      <h2 className="font-semibold">Deep Research</h2>
      {job.query && <p>{job.query}</p>}
      <p role="status">{job.status === 'queued' ? 'Istraživanje je na čekanju' :
        job.status === 'running' ? 'Istraživanje je u toku' : researchFailureMessage(job)}</p>
      <p className="text-sm text-chat-muted">Proteklo vreme: {elapsed}</p>
      {active && <p className="text-sm text-chat-muted">Detaljno istraživanje može trajati nekoliko minuta.</p>}
      <p className="text-sm text-chat-muted">Poslednje ažuriranje: {new Date(job.updated_at).toLocaleTimeString()}</p>
    </section>
  );
}
