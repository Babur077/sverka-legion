import React from 'react';
import { RefreshCw, Building2, BarChart3, Settings, LogOut, Shield, ShieldCheck, UserCheck, Zap } from 'lucide-react';
import { User } from '../types';

interface NavbarProps {
  user: User;
  currentTab: string;
  onSelectTab: (tab: string) => void;
  onLogout: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  user,
  currentTab,
  onSelectTab,
  onLogout,
}) => {
  const roleLabel = {
    admin: 'Администратор',
    accountant: 'Бухгалтер',
    auditor: 'Аудитор',
  }[user.role] || user.role;

  const roleBadgeColor = {
    admin: 'bg-indigo-50 text-indigo-700 border-indigo-200',
    accountant: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    auditor: 'bg-amber-50 text-amber-700 border-amber-200',
  }[user.role] || 'bg-slate-50 text-slate-700 border-slate-200';

  const navItems = [
    { id: 'rrn', label: 'Сверка по RRN', icon: RefreshCw, adminOnly: false },
    { id: 'epos', label: 'Реестр банков', icon: Building2, adminOnly: true },
    { id: 'analytics', label: 'Аналитика', icon: BarChart3, adminOnly: false },
    { id: 'admin', label: 'Настройки', icon: Settings, adminOnly: true },
  ].filter(item => !item.adminOnly || user.role === 'admin');

  return (
    <aside className="w-64 bg-white border-r border-slate-200 flex flex-col shrink-0 min-h-screen">
      {/* Brand Header */}
      <div className="p-5 border-b border-slate-100">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-lg bg-indigo-600 flex items-center justify-center text-white shadow-sm font-black text-lg">
            <Zap className="w-5 h-5 fill-white text-white" />
          </div>
          <div>
            <div className="font-bold text-slate-900 text-base leading-tight">ReconcileHub</div>
            <div className="text-[11px] font-semibold text-slate-400 tracking-wider">v2.0 • PROFESSIONAL</div>
          </div>
        </div>
      </div>

      {/* Navigation section */}
      <div className="p-3 flex-1">
        <div className="px-3 py-2 text-[11px] font-bold text-slate-400 uppercase tracking-wider">
          ОБЗОР
        </div>
        <nav className="space-y-1">
          {navItems.map(item => {
            const Icon = item.icon;
            const active = currentTab === item.id;
            return (
              <button
                key={item.id}
                id={`nav-item-${item.id}`}
                onClick={() => onSelectTab(item.id)}
                className={`w-full flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-sm font-medium transition-all text-left cursor-pointer ${
                  active
                    ? 'bg-indigo-50 text-indigo-700 font-semibold shadow-xs'
                    : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                }`}
              >
                <Icon className={`w-4 h-4 shrink-0 ${active ? 'text-indigo-600' : 'text-slate-400'}`} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
      </div>

      {/* User profile & Logout */}
      <div className="p-4 border-t border-slate-100 bg-slate-50/50">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2 overflow-hidden">
            <div className="w-8 h-8 rounded-full bg-slate-200 flex items-center justify-center text-slate-700 font-semibold text-xs shrink-0">
              {user.username.slice(0, 2).toUpperCase()}
            </div>
            <div className="truncate">
              <div className="text-xs font-semibold text-slate-900 truncate">{user.username}</div>
              <div className={`inline-flex items-center text-[10px] font-medium px-1.5 py-0.2 rounded border ${roleBadgeColor}`}>
                {roleLabel}
              </div>
            </div>
          </div>
        </div>

        <button
          id="logout-button"
          onClick={onLogout}
          className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg border border-slate-200 hover:border-rose-200 hover:bg-rose-50 text-xs font-medium text-slate-600 hover:text-rose-600 transition-colors cursor-pointer"
        >
          <LogOut className="w-3.5 h-3.5" />
          <span>Выйти из системы</span>
        </button>
      </div>
    </aside>
  );
};
