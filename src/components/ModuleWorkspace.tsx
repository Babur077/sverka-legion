import React, { useState, useEffect } from 'react';
import { 
  Building2, 
  CreditCard, 
  Receipt, 
  Layers, 
  CheckCircle2, 
  ShieldAlert, 
  FileSpreadsheet, 
  Upload, 
  Play, 
  BarChart3, 
  HelpCircle,
  ExternalLink,
  Users
} from 'lucide-react';
import { User, ReconciliationModuleManifest } from '../types';

interface ModuleWorkspaceProps {
  user: User;
  onSelectRrnModule: () => void;
}

export const ModuleWorkspace: React.FC<ModuleWorkspaceProps> = ({ user, onSelectRrnModule }) => {
  const [modules, setModules] = useState<ReconciliationModuleManifest[]>([
    {
      id: 'bank_rrn',
      name: 'Сверка эквайринга (RRN)',
      version: '1.4.2',
      description: 'Потранзакционная сверка 1С / АБС с выписками банков по номерам RRN, суммам и комиссиям.',
      category: 'Эквайринг',
      icon: 'CreditCard',
      author: 'Отдел эквайринга',
      status: 'active',
      required_permissions: ['bank_rrn.view', 'bank_rrn.run'],
      required_files: [
        { key: 'our_file', label: 'Реестр операций 1С / Базы данных (Excel/CSV)' },
        { key: 'bank_file', label: 'Банковская выписка эквайринга (Excel/CSV)' }
      ]
    },
    {
      id: 'paynet_agents',
      name: 'Сверка платежных систем (Paynet / Payme)',
      version: '1.0.1',
      description: 'Сверка агентских реестров с внутренним биллингом по Transaction ID, комиссиям и статусам холда.',
      category: 'Платежные системы',
      icon: 'Receipt',
      author: 'Отдел e-commerce',
      status: 'active',
      required_permissions: ['paynet.view', 'paynet.run'],
      required_files: [
        { key: 'billing_file', label: 'Выгрузка биллинга / Orders' },
        { key: 'agent_file', label: 'Реестр провайдера (Paynet/Payme)' }
      ]
    },
    {
      id: 'epos_registry',
      name: 'Сверка и учет терминалов (EPOS)',
      version: '2.1.0',
      description: 'Контроль активности терминалов, ставок комиссий и проверка корректности банковских начислений.',
      category: 'Справочники',
      icon: 'Building2',
      author: 'Финансовый контроллинг',
      status: 'active',
      required_permissions: ['epos.view'],
      required_files: []
    }
  ]);

  const [selectedModuleId, setSelectedModuleId] = useState<string>('bank_rrn');
  const [selectedCategory, setSelectedCategory] = useState<string>('Все');

  // Фильтруем модули с учетом прав пользователя
  const userPerms = user.permissions || (user.role === 'admin' ? ['*'] : [
    user.role === 'auditor' ? 'bank_rrn.view' : 'bank_rrn.run',
    'bank_rrn.view',
    'paynet.view'
  ]);

  const hasAccess = (mod: ReconciliationModuleManifest) => {
    if (user.role === 'admin' || userPerms.includes('*')) return true;
    return mod.required_permissions.some(p => userPerms.includes(p));
  };

  const categories = ['Все', 'Эквайринг', 'Платежные системы', 'Справочники'];

  const filteredModules = modules.filter(m => {
    const catMatch = selectedCategory === 'Все' || m.category === selectedCategory;
    return catMatch;
  });

  const activeModule = modules.find(m => m.id === selectedModuleId) || modules[0];
  const userCanRun = user.role !== 'auditor';

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Верхний баннер архитектуры модульного монолита */}
      <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-xs flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200">
              Модульный монолит
            </span>
            <span className="text-xs text-slate-500">FastAPI + Python Polars Core</span>
          </div>
          <h1 className="text-2xl font-bold text-slate-900">
            Реестр модулей сверок ReconcileHub
          </h1>
          <p className="text-sm text-slate-600 mt-1 max-w-2xl">
            Каждая сверка работает как независимый модуль с собственным расчетным движком, 
            набором валидаций и персональной аналитикой.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="text-right hidden sm:block">
            <div className="text-xs font-medium text-slate-500">Текущий сотрудник</div>
            <div className="text-sm font-semibold text-slate-900">{user.username} ({user.role})</div>
          </div>
          <div className="w-10 h-10 rounded-lg bg-slate-100 flex items-center justify-center text-slate-700 font-bold border border-slate-200">
            {user.username.charAt(0).toUpperCase()}
          </div>
        </div>
      </div>

      {/* Фильтр по категориям */}
      <div className="flex items-center gap-2 overflow-x-auto pb-1">
        {categories.map(cat => (
          <button
            key={cat}
            onClick={() => setSelectedCategory(cat)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
              selectedCategory === cat
                ? 'bg-indigo-600 text-white shadow-xs'
                : 'bg-white text-slate-700 border border-slate-200 hover:bg-slate-50'
            }`}
          >
            {cat}
          </button>
        ))}
      </div>

      {/* Сетка модулей */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        {filteredModules.map(mod => {
          const permitted = hasAccess(mod);
          const isSelected = selectedModuleId === mod.id;

          return (
            <div
              key={mod.id}
              onClick={() => setSelectedModuleId(mod.id)}
              className={`cursor-pointer bg-white rounded-xl border p-5 transition-all relative flex flex-col justify-between ${
                isSelected
                  ? 'border-indigo-600 ring-2 ring-indigo-600/10 shadow-sm'
                  : 'border-slate-200 hover:border-slate-300 shadow-xs'
              } ${!permitted ? 'opacity-60 bg-slate-50' : ''}`}
            >
              <div>
                <div className="flex items-start justify-between gap-3 mb-3">
                  <div className="w-10 h-10 rounded-lg bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600">
                    {mod.icon === 'CreditCard' && <CreditCard className="w-5 h-5" />}
                    {mod.icon === 'Receipt' && <Receipt className="w-5 h-5" />}
                    {mod.icon === 'Building2' && <Building2 className="w-5 h-5" />}
                  </div>

                  <div className="flex items-center gap-1.5">
                    <span className="text-[11px] font-mono text-slate-500 bg-slate-100 px-2 py-0.5 rounded">
                      v{mod.version}
                    </span>
                    {permitted ? (
                      <span className="flex items-center gap-1 text-[11px] font-medium text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                        Доступен
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-[11px] font-medium text-amber-700 bg-amber-50 px-2 py-0.5 rounded-full border border-amber-200">
                        <ShieldAlert className="w-3 h-3" />
                        Нет прав
                      </span>
                    )}
                  </div>
                </div>

                <h3 className="font-bold text-slate-900 text-base leading-snug">
                  {mod.name}
                </h3>
                <p className="text-xs text-slate-600 mt-2 line-clamp-2">
                  {mod.description}
                </p>
              </div>

              <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
                <span>{mod.author}</span>
                <span className="font-medium text-indigo-600">{mod.category}</span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Детальная карточка выбранного модуля */}
      {activeModule && (
        <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-xs space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-100">
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-xl font-bold text-slate-900">{activeModule.name}</h2>
                <span className="text-xs font-mono bg-slate-100 text-slate-600 px-2 py-0.5 rounded">
                  {activeModule.id}
                </span>
              </div>
              <p className="text-sm text-slate-600 mt-1">{activeModule.description}</p>
            </div>

            <div className="flex items-center gap-3">
              {activeModule.id === 'bank_rrn' ? (
                <button
                  onClick={onSelectRrnModule}
                  className="px-5 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold flex items-center gap-2 shadow-xs transition-colors"
                >
                  <Play className="w-4 h-4 fill-white" />
                  Перейти в рабочее место сверки
                </button>
              ) : (
                <button
                  disabled
                  className="px-5 py-2.5 rounded-lg bg-slate-100 text-slate-400 text-sm font-medium cursor-not-allowed flex items-center gap-2"
                >
                  Модуль на этапе приёмки (Draft)
                </button>
              )}
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Обязательные входные файлы по контракту */}
            <div className="space-y-3">
              <h3 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
                <FileSpreadsheet className="w-4 h-4 text-indigo-600" />
                Входные спецификации файлов (Контракт модуля):
              </h3>
              {activeModule.required_files.length > 0 ? (
                <div className="space-y-2">
                  {activeModule.required_files.map(f => (
                    <div key={f.key} className="p-3 bg-slate-50 border border-slate-200 rounded-lg text-xs flex items-center justify-between">
                      <span className="font-medium text-slate-800">{f.label}</span>
                      <span className="font-mono text-slate-500 bg-white px-2 py-0.5 rounded border border-slate-200">
                        key: {f.key}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="p-4 bg-slate-50 border border-slate-200 rounded-lg text-xs text-slate-500">
                  Модуль использует встроенные справочники базы данных.
                </div>
              )}
            </div>

            {/* Права доступа и политика безопасности */}
            <div className="space-y-3">
              <h3 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
                <ShieldAlert className="w-4 h-4 text-indigo-600" />
                Требуемые привилегии (RBAC Scopes):
              </h3>
              <div className="space-y-2">
                {activeModule.required_permissions.map(perm => {
                  const has = user.role === 'admin' || userPerms.includes('*') || userPerms.includes(perm);
                  return (
                    <div key={perm} className="p-3 bg-slate-50 border border-slate-200 rounded-lg text-xs flex items-center justify-between">
                      <span className="font-mono text-slate-700">{perm}</span>
                      {has ? (
                        <span className="text-emerald-700 font-medium flex items-center gap-1">
                          <CheckCircle2 className="w-3.5 h-3.5" />
                          Разрешено пользователю
                        </span>
                      ) : (
                        <span className="text-rose-600 font-medium">
                          Заблокировано политикой
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
