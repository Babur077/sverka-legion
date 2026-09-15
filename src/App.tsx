import React, { useState } from 'react';
import { LoginScreen } from './components/LoginScreen';
import { Navbar } from './components/Navbar';
import { RrnPage } from './components/RrnPage';
import { EposPage } from './components/EposPage';
import { AnalyticsPage } from './components/AnalyticsPage';
import { AdminPage } from './components/AdminPage';
import { ModuleWorkspace } from './components/ModuleWorkspace';
import { User, SystemSettings } from './types';
import { getStoredSettings, logAction } from './utils/storage';

export const App: React.FC = () => {
  const [user, setUser] = useState<User | null>(() => {
    try {
      const saved = sessionStorage.getItem('reconcile_active_user');
      return saved ? JSON.parse(saved) : null;
    } catch {
      return null;
    }
  });
  const [currentTab, setCurrentTab] = useState<string>('modules');
  const [settings, setSettings] = useState<SystemSettings>(getStoredSettings());

  const handleLogout = () => {
    if (user) {
      logAction(user.username, 'LOGOUT', 'Выход из системы');
    }
    try {
      sessionStorage.removeItem('reconcile_active_user');
    } catch {}
    setUser(null);
  };

  const handleLoginSuccess = (loggedInUser: User) => {
    try {
      sessionStorage.setItem('reconcile_active_user', JSON.stringify(loggedInUser));
    } catch {}
    setUser(loggedInUser);
    setCurrentTab('modules');
  };

  if (!user) {
    return <LoginScreen onLoginSuccess={handleLoginSuccess} />;
  }

  return (
    <div className="flex h-screen bg-slate-50 overflow-hidden font-sans text-slate-900">
      <Navbar
        user={user}
        currentTab={currentTab}
        onSelectTab={setCurrentTab}
        onLogout={handleLogout}
      />

      <main className="flex-1 overflow-y-auto">
        {currentTab === 'modules' && (
          <ModuleWorkspace 
            user={user} 
            onSelectRrnModule={() => setCurrentTab('rrn')} 
          />
        )}
        {currentTab === 'rrn' && <RrnPage user={user} settings={settings} />}
        {currentTab === 'epos' && user.role === 'admin' && <EposPage user={user} />}
        {currentTab === 'analytics' && <AnalyticsPage user={user} />}
        {currentTab === 'admin' && user.role === 'admin' && (
          <AdminPage user={user} settings={settings} onUpdateSettings={setSettings} />
        )}
      </main>
    </div>
  );
};

export default App;
