import React, { useEffect, useState } from 'react';
import { AlertCircle, CheckCircle2, LoaderCircle } from 'lucide-react';
import { LoginScreen } from './components/LoginScreen';
import { Navbar } from './components/Navbar';
import { RrnPage } from './components/RrnPage';
import { AdminPage } from './components/AdminPage';
import { EposPage } from './components/EposPage';
import { AuditPage } from './components/AuditPage';
import { ModuleWorkspace } from './components/ModuleWorkspace';
import { BankRrnWorkspace, BankRrnSection } from './components/BankRrnWorkspace';
import { BankRrnOverview } from './components/BankRrnOverview';
import { BankRrnAnalytics } from './components/BankRrnAnalytics';
import { BankRrnArchive } from './components/BankRrnArchive';
import { User, SystemSettings, ReconciliationModuleManifest } from './types';
import { hasModuleWorkspace, ModuleWorkspaceKey } from './modules/workspaceRegistry';
import { getSettingsViaApi } from './utils/settingsApi';
import { getCurrentUserViaApi, logoutViaApi } from './utils/authApi';
import { clearSessionToken } from './utils/apiClient';
import { hasPermission } from './utils/permissions';

interface FileParseProgressDetail {
  status: 'loading' | 'success' | 'error';
  stage: 'reading' | 'parsing' | 'ready' | 'error';
  fileName: string;
  progress?: number;
  rows?: number;
  columns?: number;
  error?: string;
  sizeBytes?: number;
  elapsedMs?: number;
}

const FILE_PARSE_PROGRESS_EVENT = 'reconcile:file-parse-progress';

function formatBytes(bytes?: number): string {
  if (!bytes) return '';
  return `${(bytes / 1024 / 1024).toFixed(bytes >= 10 * 1024 * 1024 ? 0 : 1)} МБ`;
}

function formatDuration(ms?: number): string {
  if (typeof ms !== 'number') return '';
  const totalSeconds = Math.max(0, Math.round(ms / 1000));
  if (totalSeconds < 60) return `${totalSeconds} с`;
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes} мин ${seconds.toString().padStart(2, '0')} с`;
}

const UploadProgressIndicator: React.FC = () => {
  const [progress, setProgress] = useState<FileParseProgressDetail | null>(null);
  const [liveElapsedMs, setLiveElapsedMs] = useState(0);

  useEffect(() => {
    let hideTimer: number | undefined;
    let elapsedTimer: number | undefined;
    let startedAt = 0;

    const handleProgress = (event: Event) => {
      const detail = (event as CustomEvent<FileParseProgressDetail>).detail;
      if (!detail) return;

      if (hideTimer) window.clearTimeout(hideTimer);
      if (elapsedTimer) window.clearInterval(elapsedTimer);

      if (detail.status === 'loading' && startedAt === 0) {
        startedAt = performance.now();
        setLiveElapsedMs(0);
        elapsedTimer = window.setInterval(() => {
          setLiveElapsedMs(performance.now() - startedAt);
        }, 250);
      }

      setProgress(detail);

      if (detail.status === 'success') {
        setLiveElapsedMs(detail.elapsedMs ?? performance.now() - startedAt);
        startedAt = 0;
        hideTimer = window.setTimeout(() => setProgress(null), 2500);
      } else if (detail.status === 'error') {
        setLiveElapsedMs(detail.elapsedMs ?? performance.now() - startedAt);
        startedAt = 0;
        hideTimer = window.setTimeout(() => setProgress(null), 5000);
      }
    };

    window.addEventListener(FILE_PARSE_PROGRESS_EVENT, handleProgress);
    return () => {
      window.removeEventListener(FILE_PARSE_PROGRESS_EVENT, handleProgress);
      if (hideTimer) window.clearTimeout(hideTimer);
      if (elapsedTimer) window.clearInterval(elapsedTimer);
    };
  }, []);

  // Keep the existing workspace copy in sync with the real upload limit while an older cached bundle is in use.
  useEffect(() => {
    const replaceLegacyLimit = () => {
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      let node: Node | null;
      while ((node = walker.nextNode())) {
        if (node.nodeValue?.includes('до 50 МБ')) {
          node.nodeValue = node.nodeValue.split('до 50 МБ').join('до 200 МБ');
        }
      }
    };

    replaceLegacyLimit();
    const observer = new MutationObserver(replaceLegacyLimit);
    observer.observe(document.body, { childList: true, subtree: true, characterData: true });
    return () => observer.disconnect();
  }, []);

  if (!progress) return null;

  const isError = progress.status === 'error';
  const isSuccess = progress.status === 'success';
  const elapsedMs = progress.elapsedMs ?? liveElapsedMs;
  const fileMeta = [formatBytes(progress.sizeBytes), formatDuration(elapsedMs)].filter(Boolean).join(' · ');

  const title = isError
    ? 'Не удалось обработать файл'
    : isSuccess
      ? 'Файл готов'
      : progress.stage === 'reading'
        ? 'Чтение файла…'
        : 'Обработка Excel / CSV…';

  const subtitle = isError
    ? (progress.error || 'Проверьте формат файла и попробуйте ещё раз.')
    : isSuccess
      ? `${progress.rows ?? 0} строк · ${progress.columns ?? 0} колонок${fileMeta ? ` · ${fileMeta}` : ''}`
      : `${progress.fileName}${fileMeta ? ` · ${fileMeta}` : ''}`;

  return (
    <div className="fixed top-4 right-4 z-[100] w-[min(420px,calc(100vw-2rem))] rounded-2xl border border-slate-200 bg-white/95 p-4 shadow-xl backdrop-blur-md">
      <div className="flex items-start gap-3">
        <div className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${
          isError ? 'bg-rose-50 text-rose-600' : isSuccess ? 'bg-emerald-50 text-emerald-600' : 'bg-indigo-50 text-indigo-600'
        }`}>
          {isError ? <AlertCircle className="h-4 w-4" /> : isSuccess ? <CheckCircle2 className="h-4 w-4" /> : <LoaderCircle className="h-4 w-4 animate-spin" />}
        </div>

        <div className="min-w-0 flex-1">
          <div className="text-sm font-bold text-slate-900">{title}</div>
          <div className="mt-0.5 truncate text-xs text-slate-500" title={subtitle}>{subtitle}</div>

          {!isError && !isSuccess && (
            <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-slate-100">
              {progress.stage === 'reading' ? (
                <div
                  className="h-full rounded-full bg-indigo-600 transition-[width] duration-200"
                  style={{ width: `${Math.max(3, progress.progress ?? 0)}%` }}
                />
              ) : (
                <div className="h-full w-1/3 animate-pulse rounded-full bg-indigo-600" />
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export const App: React.FC = () => {
  const [user, setUser] = useState<User | null>(() => {
    try {
      const saved = sessionStorage.getItem('reconcile_active_user');
      return saved ? JSON.parse(saved) : null;
    } catch { return null; }
  });
  const [currentTab, setCurrentTab] = useState<string>('modules');
  const [activeModuleWorkspace, setActiveModuleWorkspace] = useState<ModuleWorkspaceKey | null>(null);
  const [bankSection, setBankSection] = useState<BankRrnSection>('overview');
  const [settings, setSettings] = useState<SystemSettings>({ amount_tolerance: 0.01, currency: 'UZS', dayfirst: true });

  useEffect(() => {
    if (!user) return;
    void getSettingsViaApi(user.username).then(setSettings).catch(() => {
      // Keep safe defaults if the settings endpoint is temporarily unavailable.
    });
  }, [user?.username]);

  useEffect(() => {
    if (!user) return;
    void getCurrentUserViaApi(user.username).then(refreshed => {
      setUser(current => {
        if (!current || current.username !== refreshed.username) return current;
        try { sessionStorage.setItem('reconcile_active_user', JSON.stringify(refreshed)); } catch {}
        return refreshed;
      });
    }).catch(() => {
      clearSessionToken();
      try { sessionStorage.removeItem('reconcile_active_user'); } catch {}
      setUser(null);
    });
  }, [user?.username, currentTab]);

  const handleLogout = () => {
    void logoutViaApi();
    try { sessionStorage.removeItem('reconcile_active_user'); } catch {}
    setUser(null);
  };

  const handleLoginSuccess = (loggedInUser: User) => {
    try { sessionStorage.setItem('reconcile_active_user', JSON.stringify(loggedInUser)); } catch {}
    setUser(loggedInUser);
    setCurrentTab('modules');
    setActiveModuleWorkspace(null);
    setBankSection('overview');
  };

  if (!user) return <LoginScreen onLoginSuccess={handleLoginSuccess} />;

  const openModule = (module: ReconciliationModuleManifest) => {
    if (!hasModuleWorkspace(module.workspace)) return;
    setActiveModuleWorkspace(module.workspace);
    setCurrentTab('module');

    if (module.workspace === 'bank_rrn') {
      setBankSection(
        hasPermission(user, 'bank_rrn.view')
          ? 'overview'
          : hasPermission(user, 'bank_rrn.run')
            ? 'workspace'
            : hasPermission(user, 'epos.view') || hasPermission(user, 'epos.manage')
              ? 'registry'
              : hasPermission(user, 'analytics.view_all')
                ? 'analytics'
                : hasPermission(user, 'archive.view')
                  ? 'archive'
                  : 'overview',
      );
    }
  };

  const renderBankSection = () => {
    switch (bankSection) {
      case 'workspace':
        return <RrnPage user={user} settings={settings} />;
      case 'registry':
        return <EposPage user={user} />;
      case 'analytics':
        return <BankRrnAnalytics user={user} />;
      case 'archive':
        return <BankRrnArchive user={user} onNewReconciliation={() => setBankSection('workspace')} />;
      case 'overview':
      default:
        return <BankRrnOverview user={user} onStart={() => setBankSection('workspace')} />;
    }
  };

  const renderActiveModule = () => {
    switch (activeModuleWorkspace) {
      case 'bank_rrn':
        return (
          <BankRrnWorkspace
            user={user}
            activeSection={bankSection}
            onNavigate={setBankSection}
            onBack={() => {
              setActiveModuleWorkspace(null);
              setCurrentTab('modules');
            }}
            onOpenReconciliation={() => setBankSection('workspace')}
          >
            {renderBankSection()}
          </BankRrnWorkspace>
        );
      default:
        return null;
    }
  };

  return (
    <div className="flex h-screen bg-slate-50 overflow-hidden font-sans text-slate-900">
      <UploadProgressIndicator />
      {currentTab !== 'module' && <Navbar user={user} currentTab={currentTab} onSelectTab={setCurrentTab} onLogout={handleLogout} />}
      <main className="flex-1 overflow-y-auto">
        {currentTab === 'modules' && <ModuleWorkspace user={user} onOpenModule={openModule} />}
        {currentTab === 'module' && renderActiveModule()}
        {currentTab === 'audit' && <AuditPage user={user} />}
        {currentTab === 'admin' && hasPermission(user, '*') && <AdminPage user={user} settings={settings} onUpdateSettings={setSettings} />}
      </main>
    </div>
  );
};

export default App;
