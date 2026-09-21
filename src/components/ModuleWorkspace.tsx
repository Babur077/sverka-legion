import React, { useEffect, useMemo, useState } from 'react';
import {
  CheckCircle2,
  CreditCard,
  FileSpreadsheet,
  Layers,
  Play,
  Receipt,
  RefreshCw,
  ShieldAlert,
  Wrench,
  Building2,
} from 'lucide-react';
import { ReconciliationModuleManifest, User } from '../types';
import { hasModuleWorkspace } from '../modules/workspaceRegistry';
import { getModulesViaApi } from '../utils/modulesApi';

interface ModuleWorkspaceProps {
  user: User;
  onOpenModule: (module: ReconciliationModuleManifest) => void;
}

const iconFor = (name: string) => {
  if (name === 'CreditCard') return CreditCard;
  if (name === 'Receipt') return Receipt;
  if (name === 'Wrench') return Wrench;
  if (name === 'Building2') return Building2;
  return Layers;
};

export const ModuleWorkspace: React.FC<ModuleWorkspaceProps> = ({ user, onOpenModule }) => {
  const [modules, setModules] = useState<ReconciliationModuleManifest[]>([]);
  const [selectedModuleId, setSelectedModuleId] = useState<string>('');
  const [selectedCategory, setSelectedCategory] = useState<string>('Все');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadModules = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getModulesViaApi(user.username);
      setModules(data);
      setSelectedModuleId(current => {
        if (current && data.some(module => module.id === current)) return current;
        return data[0]?.id || '';
      });
    } catch (err: any) {
      setError(err?.message || 'Не удалось загрузить реестр модулей.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadModules();
  }, [user.username]);

  const categories = useMemo(
    () => ['Все', ...Array.from(new Set(modules.map(module => module.category).filter(Boolean)))],
    [modules],
  );

  const filteredModules = useMemo(
    () => modules.filter(module => selectedCategory === 'Все' || module.category === selectedCategory),
    [modules, selectedCategory],
  );

  const activeModule = modules.find(module => module.id === selectedModuleId) || modules[0];
  const userPermissions = user.permissions || [];
  const canOpenCurrentWorkspace = activeModule?.status === 'active' && hasModuleWorkspace(activeModule?.workspace);

  return (
    <div className="w-full max-w-[1800px] mx-auto p-6 xl:px-8 space-y-6">
      <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-xs flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200">
              Реестр модулей
            </span>
            <span className="text-xs text-slate-500">FastAPI + Python reconciliation modules</span>
          </div>
          <h1 className="text-2xl font-bold text-slate-900">Модули сверок ReconcileHub</h1>
          <p className="text-sm text-slate-600 mt-1 max-w-2xl">
            Здесь отображаются только реально зарегистрированные backend-модули. Новая сверка появляется в реестре после регистрации её манифеста и движка.
          </p>
        </div>

        <button
          onClick={() => void loadModules()}
          disabled={loading}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          Обновить реестр
        </button>
      </div>

      {error && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-xs text-rose-700">
          {error}
        </div>
      )}

      {!loading && modules.length === 0 ? (
        <div className="bg-white border border-slate-200 rounded-xl p-12 text-center shadow-xs">
          <Layers className="w-8 h-8 text-slate-300 mx-auto" />
          <h2 className="mt-3 text-sm font-bold text-slate-900">Нет доступных модулей</h2>
          <p className="mt-1 text-xs text-slate-500">
            Для пользователя нет зарегистрированных сверок с подходящими правами доступа.
          </p>
        </div>
      ) : (
        <>
          <div className="flex items-center gap-2 overflow-x-auto pb-1">
            {categories.map(category => (
              <button
                key={category}
                onClick={() => setSelectedCategory(category)}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                  selectedCategory === category
                    ? 'bg-indigo-600 text-white shadow-xs'
                    : 'bg-white text-slate-700 border border-slate-200 hover:bg-slate-50'
                }`}
              >
                {category}
              </button>
            ))}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
            {filteredModules.map(module => {
              const Icon = iconFor(module.icon);
              const selected = module.id === activeModule?.id;

              return (
                <button
                  key={module.id}
                  type="button"
                  onClick={() => setSelectedModuleId(module.id)}
                  className={`text-left bg-white rounded-xl border p-5 transition-all relative flex flex-col justify-between ${
                    selected
                      ? 'border-indigo-600 ring-2 ring-indigo-600/10 shadow-sm'
                      : 'border-slate-200 hover:border-slate-300 shadow-xs'
                  }`}
                >
                  <div>
                    <div className="flex items-start justify-between gap-3 mb-3">
                      <div className="w-10 h-10 rounded-lg bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600">
                        <Icon className="w-5 h-5" />
                      </div>
                      <div className="flex items-center gap-1.5">
                        <span className="text-[11px] font-mono text-slate-500 bg-slate-100 px-2 py-0.5 rounded">
                          v{module.version}
                        </span>
                        <span className={`flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-full border ${
                          module.status === 'active'
                            ? 'text-emerald-700 bg-emerald-50 border-emerald-200'
                            : module.status === 'draft'
                              ? 'text-amber-700 bg-amber-50 border-amber-200'
                              : 'text-slate-600 bg-slate-50 border-slate-200'
                        }`}>
                          <span className={`w-1.5 h-1.5 rounded-full ${
                            module.status === 'active'
                              ? 'bg-emerald-500'
                              : module.status === 'draft'
                                ? 'bg-amber-500'
                                : 'bg-slate-400'
                          }`} />
                          {module.status === 'active' ? 'Активен' : module.status === 'draft' ? 'Черновик' : 'Устарел'}
                        </span>
                      </div>
                    </div>

                    <h3 className="font-bold text-slate-900 text-base leading-snug">{module.name}</h3>
                    <p className="text-xs text-slate-600 mt-2 line-clamp-2">{module.description}</p>
                  </div>

                  <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
                    <span>{module.author}</span>
                    <span className="font-medium text-indigo-600">{module.category}</span>
                  </div>
                </button>
              );
            })}
          </div>

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

                {canOpenCurrentWorkspace ? (
                  <button
                    onClick={() => onOpenModule(activeModule)}
                    className="px-5 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold flex items-center gap-2 shadow-xs transition-colors"
                  >
                    <Play className="w-4 h-4 fill-white" />
                    Перейти в рабочее место сверки
                  </button>
                ) : (
                  <span className="text-xs text-slate-500 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2">
                    {activeModule.status !== 'active'
                      ? 'Модуль пока не активирован для запуска.'
                      : 'Backend-модуль зарегистрирован. Для рабочего места укажите workspace в manifest и добавьте UI в workspace registry.'}
                  </span>
                )}
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="space-y-3">
                  <h3 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
                    <FileSpreadsheet className="w-4 h-4 text-indigo-600" />
                    Входные файлы по контракту
                  </h3>
                  {activeModule.required_files.length ? (
                    <div className="space-y-2">
                      {activeModule.required_files.map(file => (
                        <div key={file.key} className="p-3 bg-slate-50 border border-slate-200 rounded-lg text-xs flex items-center justify-between gap-3">
                          <span className="font-medium text-slate-800">{file.label}</span>
                          <span className="font-mono text-slate-500 bg-white px-2 py-0.5 rounded border border-slate-200">
                            {file.key}
                          </span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="p-4 bg-slate-50 border border-slate-200 rounded-lg text-xs text-slate-500">
                      Внешние файлы не требуются.
                    </div>
                  )}
                </div>

                <div className="space-y-3">
                  <h3 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
                    <ShieldAlert className="w-4 h-4 text-indigo-600" />
                    RBAC scopes
                  </h3>
                  <div className="space-y-2">
                    {activeModule.required_permissions.map(permission => {
                      const allowed = userPermissions.includes('*') || userPermissions.includes(permission);
                      return (
                        <div key={permission} className="p-3 bg-slate-50 border border-slate-200 rounded-lg text-xs flex items-center justify-between">
                          <span className="font-mono text-slate-700">{permission}</span>
                          {allowed ? (
                            <span className="text-emerald-700 font-medium flex items-center gap-1">
                              <CheckCircle2 className="w-3.5 h-3.5" />
                              Разрешено
                            </span>
                          ) : (
                            <span className="text-rose-600 font-medium">Нет права</span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
};
