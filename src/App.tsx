import React, { useState } from 'react';
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
