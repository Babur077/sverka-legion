import React, { useState } from 'react';
import {
  ArrowLeft,
  BarChart3,
  Building2,
  ChevronRight,
  FileClock,
  History,
  LayoutDashboard,
  Play,
  Settings2,
} from 'lucide-react';
import { User } from '../types';

export type BankRrnSection = 'overview' | 'workspace' | 'registry' | 'analytics' | 'archive';

interface BankRrnWorkspaceProps {
  user: User;
  activeSection?: BankRrnSection;
  onNavigate: (section: BankRrnSection) => void;
  onBack: () => void;
  onOpenReconciliation: () => void;
  children?: React.ReactNode;
}

const menuItems: Array<{
  id: BankRrnSection;
  label: string;
  description: string;
  icon: React.ElementType;
}> = [
  { id: 'overview', label: 'Обзор', description: 'Состояние сверки и последние запуски', icon: LayoutDashboard },
  { id: 'workspace', label: 'Новая сверка', description: 'Загрузить данные и запустить сверку', icon: Play },
  { id: 'registry', label: 'Реестр банков', description: 'Банки, комиссии и терминалы', icon: Building2 },
  { id: 'analytics', label: 'Аналитика', description: 'Метрики и динамика сверки', icon: BarChart3 },
  { id: 'archive', label: 'Архив', description: 'История запусков и результаты', icon: History },
];

export const BankRrnWorkspace: React.FC<BankRrnWorkspaceProps> = ({
  user,
  activeSection = 'overview',
  onNavigate,
  onBack,
  onOpenReconciliation,
  children,
}) => {
  const [collapsed, setCollapsed] = useState(false);
  const active = menuItems.find((item) => item.id === activeSection) ?? menuItems[0];

  return (
    <div className="min-h-full bg-slate-50">
      <div className="sticky top-0 z-20 bg-white/95 backdrop-blur border-b border-slate-200">
        <div className="w-full max-w-[1800px] mx-auto px-4 md:px-6 xl:px-8 py-4">
          <button
            onClick={onBack}
            className="inline-flex items-center gap-2 text-xs font-semibold text-slate-500 hover:text-slate-900 transition-colors"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            Все модули сверок
          </button>

          <div className="mt-3 flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
            <div className="flex items-center gap-3 min-w-0">
              <div className="w-11 h-11 rounded-xl bg-indigo-50 border border-indigo-100 text-indigo-600 flex items-center justify-center shrink-0">
                <Building2 className="w-5 h-5" />
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <h1 className="text-xl font-bold text-slate-900">Сверка банков</h1>
                  <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-slate-100 text-slate-500">bank_rrn</span>
                  <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">Активен</span>
                </div>
                <p className="text-xs text-slate-500 mt-1 truncate">Эквайринг · RRN · комиссии · терминалы</p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={onOpenReconciliation}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold shadow-sm transition-colors"
              >
                <Play className="w-3.5 h-3.5 fill-white" />
                Новая сверка
              </button>
              <button
                onClick={() => onNavigate('workspace')}
                className="p-2 rounded-lg border border-slate-200 text-slate-500 hover:text-slate-900 hover:bg-slate-50 transition-colors"
                title="Открыть новую сверку"
                aria-label="Открыть новую сверку"
              >
                <Settings2 className="w-4 h-4" />
              </button>
              <div className="hidden sm:flex items-center gap-2 pl-2 border-l border-slate-200 ml-1">
                <div className="w-8 h-8 rounded-full bg-indigo-100 text-indigo-700 flex items-center justify-center font-bold text-xs border border-indigo-200">
                  {user.username.slice(0, 2).toUpperCase()}
                </div>
                <div className="hidden md:block">
                  <div className="text-xs font-semibold text-slate-900 leading-tight">{user.username}</div>
                  <div className="text-[10px] text-slate-500">{user.role}</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="w-full max-w-[1800px] mx-auto px-4 md:px-6 xl:px-8 py-5">
        <div className="grid grid-cols-1 md:grid-cols-[260px_minmax(0,1fr)] gap-5 items-start">
          <aside className={`bg-white border border-slate-200 rounded-xl p-2 shadow-xs md:sticky md:top-32 transition-all ${collapsed ? 'md:w-20' : ''}`}>
            <div className="flex items-center justify-between px-2 py-2 mb-1">
              {!collapsed && <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Сверка банков</span>}
              <button
                onClick={() => setCollapsed((value) => !value)}
                className="ml-auto p-1.5 rounded-md text-slate-400 hover:text-slate-700 hover:bg-slate-50"
                title={collapsed ? 'Развернуть' : 'Свернуть'}
              >
                <ChevronRight className={`w-4 h-4 transition-transform ${collapsed ? '' : 'rotate-180'}`} />
              </button>
            </div>

            <nav className="space-y-1">
              {menuItems.map((item) => {
                const Icon = item.icon;
                const selected = activeSection === item.id;
                return (
                  <button
                    key={item.id}
                    onClick={() => onNavigate(item.id)}
                    title={collapsed ? item.label : undefined}
                    className={`w-full rounded-lg flex items-center gap-3 px-3 py-2.5 text-left transition-all ${
                      selected
                        ? 'bg-indigo-50 text-indigo-700 ring-1 ring-inset ring-indigo-100'
                        : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                    } ${collapsed ? 'justify-center px-0' : ''}`}
                  >
                    <Icon className={`w-4 h-4 shrink-0 ${selected ? 'text-indigo-600' : 'text-slate-400'}`} />
                    {!collapsed && (
                      <div className="min-w-0">
                        <div className="text-sm font-semibold truncate">{item.label}</div>
                        <div className="text-[10px] text-slate-400 truncate mt-0.5">{item.description}</div>
                      </div>
                    )}
                  </button>
                );
              })}
            </nav>
          </aside>

          <main className="min-w-0">
            <div className="mb-4 flex items-center justify-between gap-4">
              <div>
                <div className="text-xs font-semibold text-indigo-600 uppercase tracking-wider">Рабочее пространство</div>
                <h2 className="text-2xl font-bold text-slate-900 mt-1">{active.label}</h2>
                <p className="text-sm text-slate-500 mt-1">{active.description}</p>
              </div>
              <div className="hidden sm:flex items-center gap-2 text-xs text-slate-400">
                <FileClock className="w-4 h-4" />
                Модульная область
              </div>
            </div>

            {children}
          </main>
        </div>
      </div>
    </div>
  );
};
