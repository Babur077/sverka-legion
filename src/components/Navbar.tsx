import React, { useState } from 'react';
import { Settings, LogOut, Zap, ChevronLeft, ChevronRight, Menu, X, Layers, History, Wrench } from 'lucide-react';
import { User } from '../types';
import { hasPermission } from '../utils/permissions';

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
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  const roleLabel: Record<string, string> = {
    admin: 'Администратор',
    accountant: 'Бухгалтер эквайринга',
    accountant_acquiring: 'Бухгалтер эквайринга',
    auditor: 'Аудитор',
    finance_manager: 'Фин. менеджер',
  };
  const currentRoleLabel = roleLabel[user.role] || user.role;

  const roleBadgeColor: Record<string, string> = {
    admin: 'bg-indigo-50 text-indigo-700 border-indigo-200',
    accountant: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    accountant_acquiring: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    auditor: 'bg-amber-50 text-amber-700 border-amber-200',
    finance_manager: 'bg-purple-50 text-purple-700 border-purple-200',
  };
  const currentRoleBadgeColor = roleBadgeColor[user.role] || 'bg-slate-50 text-slate-700 border-slate-200';

  const navItems = [
    {
      id: 'modules',
      label: 'Модули сверок',
      icon: Layers,
      requiredPermission: null,
    },
    {
      id: 'constructor',
      label: 'Конструктор сверок',
      icon: Wrench,
      requiredPermission: 'reconciliation_builder.view',
    },
    {
      id: 'audit',
      label: 'Аудит',
      icon: History,
      requiredPermission: 'audit.view',
    },
    {
      id: 'admin',
      label: 'Администрирование',
      icon: Settings,
      requiredPermission: '*',
    },
  ].filter(item => !item.requiredPermission || hasPermission(user, item.requiredPermission));

  const handleItemClick = (tabId: string) => {
    onSelectTab(tabId);
    setMobileOpen(false);
  };

  return (
    <>
      {/* Mobile top bar with hamburger toggle */}
      <div className="md:hidden fixed top-0 left-0 right-0 h-14 bg-white border-b border-slate-200 z-40 px-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center text-white shadow-xs">
            <Zap className="w-4 h-4 fill-white text-white" />
          </div>
          <span className="font-bold text-slate-900 text-sm">ReconcileHub</span>
        </div>
        <button
          onClick={() => setMobileOpen(!mobileOpen)}
          className="p-2 text-slate-600 hover:text-slate-900 rounded-lg hover:bg-slate-100"
          aria-label="Toggle navigation"
        >
          {mobileOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
        </button>
      </div>

      {/* Mobile Backdrop */}
      {mobileOpen && (
        <div 
          onClick={() => setMobileOpen(false)} 
          className="md:hidden fixed inset-0 bg-slate-900/40 backdrop-blur-xs z-40 transition-opacity" 
        />
      )}

      {/* Sidebar container (responsive) */}
      <aside
        className={`fixed md:static inset-y-0 left-0 z-50 bg-white border-r border-slate-200 flex flex-col shrink-0 h-full transition-all duration-200 ease-in-out ${
          collapsed ? 'w-20' : 'w-64'
        } ${
          mobileOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'
        }`}
      >
        {/* Brand Header */}
        <div className="p-4 border-b border-slate-100 flex items-center justify-between relative">
          <div className="flex items-center gap-2.5 overflow-hidden">
            <div className="w-9 h-9 rounded-lg bg-indigo-600 flex items-center justify-center text-white shadow-xs font-black text-lg shrink-0">
              <Zap className="w-5 h-5 fill-white text-white" />
            </div>
            {!collapsed && (
              <div className="min-w-0">
                <div className="font-bold text-slate-900 text-base leading-tight truncate">ReconcileHub</div>
                <div className="text-[10px] font-semibold text-slate-400 tracking-wider">v2.0 • PROFESSIONAL</div>
              </div>
            )}
          </div>

          {/* Collapse toggle (desktop only) */}
          <button
            onClick={() => setCollapsed(!collapsed)}
            className="hidden md:flex p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors cursor-pointer"
            title={collapsed ? 'Развернуть меню' : 'Свернуть меню'}
          >
            {collapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
          </button>
        </div>

        {/* Navigation items */}
        <div className="p-3 flex-1 overflow-y-auto">
          {!collapsed && (
            <div className="px-3 py-2 text-[11px] font-bold text-slate-400 uppercase tracking-wider">
              ОБЗОР
            </div>
          )}
          <nav className="space-y-1">
            {navItems.map(item => {
              const Icon = item.icon;
              const active = currentTab === item.id;
              return (
                <button
                  key={item.id}
                  id={`nav-item-${item.id}`}
                  onClick={() => handleItemClick(item.id)}
                  title={collapsed ? item.label : undefined}
                  className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all text-left cursor-pointer ${
                    active
                      ? 'bg-indigo-50 text-indigo-700 font-semibold shadow-xs'
                      : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                  } ${collapsed ? 'justify-center px-0' : ''}`}
                >
                  <Icon className={`w-4 h-4 shrink-0 ${active ? 'text-indigo-600' : 'text-slate-400'}`} />
                  {!collapsed && <span className="truncate">{item.label}</span>}
                </button>
              );
            })}
          </nav>
        </div>

        {/* User profile & Logout */}
        <div className="p-3 border-t border-slate-100 bg-slate-50/50">
          <div className={`flex items-center gap-2 overflow-hidden mb-3 ${collapsed ? 'justify-center' : ''}`}>
            <div className="w-8 h-8 rounded-full bg-indigo-100 text-indigo-700 flex items-center justify-center font-bold text-xs shrink-0 border border-indigo-200">
              {user.username.slice(0, 2).toUpperCase()}
            </div>
            {!collapsed && (
              <div className="min-w-0 flex-1">
                <div className="text-xs font-semibold text-slate-900 truncate">{user.username}</div>
                <span className={`inline-block text-[10px] font-semibold px-2 py-0.5 rounded-full border ${currentRoleBadgeColor}`}>
                  {currentRoleLabel}
                </span>
              </div>
            )}
          </div>

          <button
            id="logout-button"
            onClick={onLogout}
            title={collapsed ? 'Выйти из системы' : undefined}
            className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg border border-slate-200 hover:border-rose-200 hover:bg-rose-50 text-xs font-medium text-slate-600 hover:text-rose-600 transition-colors cursor-pointer ${
              collapsed ? 'justify-center px-0' : 'justify-center'
            }`}
          >
            <LogOut className="w-3.5 h-3.5 shrink-0" />
            {!collapsed && <span>Выйти</span>}
          </button>
        </div>
      </aside>
    </>
  );
};
