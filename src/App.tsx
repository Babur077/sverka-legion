import React, { useEffect, useState } from 'react';
import { AlertCircle, CheckCircle2, LoaderCircle } from 'lucide-react';
import { LoginScreen } from './components/LoginScreen';
import { Navbar } from './components/Navbar';
import { RrnPage } from './components/RrnPage';
import { AnalyticsPage } from './components/AnalyticsPage';
import { AdminPage } from './components/AdminPage';
import { EposPage } from './components/EposPage';
import { ModuleWorkspace } from './components/ModuleWorkspace';
import { BankRrnWorkspace, BankRrnSection } from './components/BankRrnWorkspace';
import { BankRrnOverview } from './components/BankRrnOverview';
import { BankRrnAnalytics } from './components/BankRrnAnalytics';
import { BankRrnArchive } from './components/BankRrnArchive';
import { User, SystemSettings } from './types';
import { getStoredSettings, logAction } from './utils/storage';

interface FileParseProgressDetail {
  status: 'loading' | 'success' | 'error';
  stage: 'reading' | 'parsing' | 'ready' | 'error';
  fileName: string;
  progress?: number;
  rows?: number;
  columns?: number;
  error?: string;
}

const FILE_PARSE_PROGRESS_EVENT = 'reconcile:file-parse-progress';

const UploadProgressIndicator: React.FC = () => {
  const [progress, setProgress] = useState<FileParseProgressDetail | null>(null);

  useEffect(() => {
    let hideTimer: number | undefined;

    const handleProgress = (event: Event) => {
      const detail = (event as CustomEvent<FileParseProgressDetail>).detail;
      if (!detail) return;

      if (hideTimer) window.clearTimeout(hideTimer);
      setProgress(detail);

      if (detail.status === 'success') {
        hideTimer = window.setTimeout(() => setProgress(null), 1800);
      } else if (detail.status === 'error') {
        hideTimer = window.setTimeout(() => setProgress(null), 5000);
      }
    };

    window.addEventListener(FILE_PARSE_PROGRESS_EVENT, handleProgress);
    return () => {
      window.removeEventListener(FILE_PARSE_PROGRESS_EVENT, handleProgress);
      if (hideTimer) window.clearTimeout(hideTimer);
    };
  }, []);

  if (!progress) return null;

  const isError = progress.status === 'error';
  const isSuccess = progress.status === 'success';
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
      ? `${progress.rows ?? 0} строк · ${progress.columns ?? 0} колонок`
      : progress.fileName;

  return (
    <div className="fixed top-4 right-4 z-[100] w-[min(380px,calc(100vw-2rem))] rounded-2xl border border-slate-200 bg-white/95 p-4 shadow-xl backdrop-blur-md">
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
  const [bankSection, setBankSection] = useState<BankRrnSection>('overview');
  const [settings, setSettings] = useState<SystemSettings>(getStoredSettings());

  const handleLogout = () => {
    if (user) logAction(user.username, 'LOGOUT', 'Выход из системы');
    try { sessionStorage.removeItem('reconcile_active_user'); } catch {}
    setUser(null);
  };

  const handleLoginSuccess = (loggedInUser: User) => {
    try { sessionStorage.setItem('reconcile_active_user', JSON.stringify(loggedInUser)); } catch {}
    setUser(loggedInUser);
    setCurrentTab('modules');
    setBankSection('overview');
  };

  if (!user) return <LoginScreen onLoginSuccess={handleLoginSuccess} />;

  const openBankRrn = () => {
    setCurrentTab('bank_rrn');
    setBankSection('overview');
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

  return (
    <div className="flex h-screen bg-slate-50 overflow-hidden font-sans text-slate-900">
      <UploadProgressIndicator />
      {currentTab !== 'bank_rrn' && <Navbar user={user} currentTab={currentTab} onSelectTab={setCurrentTab} onLogout={handleLogout} />}
      <main className="flex-1 overflow-y-auto">
        {currentTab === 'modules' && <ModuleWorkspace user={user} onSelectRrnModule={openBankRrn} />}
        {currentTab === 'bank_rrn' && <BankRrnWorkspace user={user} activeSection={bankSection} onNavigate={setBankSection} onBack={() => setCurrentTab('modules')} onOpenReconciliation={() => setBankSection('workspace')}>{renderBankSection()}</BankRrnWorkspace>}
        {currentTab === 'analytics' && <AnalyticsPage user={user} />}
        {currentTab === 'epos' && user.role === 'admin' && <EposPage user={user} />}
        {currentTab === 'admin' && user.role === 'admin' && <AdminPage user={user} settings={settings} onUpdateSettings={setSettings} />}
      </main>
    </div>
  );
};

export default App;
