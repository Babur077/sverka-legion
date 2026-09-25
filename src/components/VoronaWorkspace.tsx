import React, { useEffect, useState } from 'react';
import { ArrowLeft, Database, ExternalLink, LoaderCircle, RefreshCw, ShieldCheck } from 'lucide-react';
import { User } from '../types';
import { openVoronaSession } from '../utils/voronaApi';

interface VoronaWorkspaceProps {
  user: User;
  onBack: () => void;
}

export const VoronaWorkspace: React.FC<VoronaWorkspaceProps> = ({ user, onBack }) => {
  const [url, setUrl] = useState<string>('');
  const [error, setError] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [frameKey, setFrameKey] = useState(0);

  const openWorkspace = async () => {
    setLoading(true);
    setError('');
    try {
      setUrl(await openVoronaSession());
    } catch (err: any) {
      setError(err?.message || 'Не удалось открыть Сверку Vorona.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void openWorkspace();
  }, [user.username]);

  return (
    <div className="flex h-screen min-h-0 flex-col bg-slate-50">
      <header className="shrink-0 border-b border-slate-200 bg-white px-5 py-3 shadow-sm">
        <div className="mx-auto flex max-w-[1900px] items-center justify-between gap-4">
          <div className="flex min-w-0 items-center gap-3">
            <button
              type="button"
              onClick={onBack}
              className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-slate-200 text-slate-600 transition hover:bg-slate-50"
              title="Назад к модулям"
            >
              <ArrowLeft className="h-4 w-4" />
            </button>
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600 ring-1 ring-indigo-100">
              <Database className="h-5 w-5" />
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="truncate text-lg font-bold text-slate-900">Сверка Vorona</h1>
                <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-700 ring-1 ring-emerald-200">
                  <ShieldCheck className="h-3 w-3" />
                  PostgreSQL VORONA
                </span>
              </div>
              <p className="truncate text-xs text-slate-500">Produced by Diyorbek Allayarov · оригинальная логика сохранена</p>
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-2">
            <button
              type="button"
              onClick={() => {
                if (!url) void openWorkspace();
                else setFrameKey(value => value + 1);
              }}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-600 transition hover:bg-slate-50"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              Обновить
            </button>
            {url && (
              <a
                href={url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-3 py-2 text-xs font-semibold text-white transition hover:bg-indigo-700"
              >
                <ExternalLink className="h-3.5 w-3.5" />
                В отдельном окне
              </a>
            )}
          </div>
        </div>
      </header>

      <main className="min-h-0 flex-1 p-3 lg:p-4">
        <div className="mx-auto h-full max-w-[1900px] overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          {loading ? (
            <div className="flex h-full items-center justify-center gap-3 text-sm text-slate-500">
              <LoaderCircle className="h-5 w-5 animate-spin text-indigo-600" />
              Подключение к Vorona…
            </div>
          ) : error ? (
            <div className="flex h-full items-center justify-center p-8">
              <div className="max-w-lg rounded-xl border border-rose-200 bg-rose-50 p-5 text-center">
                <div className="text-sm font-bold text-rose-800">Vorona не открылась</div>
                <div className="mt-2 text-xs leading-5 text-rose-700">{error}</div>
                <button
                  type="button"
                  onClick={() => void openWorkspace()}
                  className="mt-4 rounded-lg bg-rose-700 px-4 py-2 text-xs font-semibold text-white"
                >
                  Повторить
                </button>
              </div>
            </div>
          ) : (
            <iframe
              key={frameKey}
              title="Сверка Vorona"
              src={url}
              className="h-full w-full border-0 bg-white"
            />
          )}
        </div>
      </main>
    </div>
  );
};
