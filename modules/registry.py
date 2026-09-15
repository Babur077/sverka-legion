"""
Реестр модулей сверок платформы ReconcileHub.
Управляет регистрацией, версиями и получением активных модулей.
"""
from typing import Dict, List, Optional
from modules.base import BaseReconciliationModule, ModuleManifest
from modules.bank_rrn.engine import BankRrnModule
from modules.paynet.engine import PaynetModule


class ModuleRegistry:
    """Центральный реестр сверок (Modular Monolith)"""

    def __init__(self):
        self._modules: Dict[str, BaseReconciliationModule] = {}
        # Регистрируем встроенные модули
        self.register(BankRrnModule())
        self.register(PaynetModule())

    def register(self, module: BaseReconciliationModule):
        """Регистрация модуля в платформе"""
        self._modules[module.manifest.id] = module

    def get_module(self, module_id: str) -> Optional[BaseReconciliationModule]:
        """Получить модуль по ID"""
        return self._modules.get(module_id)

    def list_manifests(self, user_permissions: Optional[List[str]] = None) -> List[ModuleManifest]:
        """
        Возвращает список манифестов модулей.
        Если переданы права пользователя — фильтрует модули, к которым у него есть доступ!
        """
        manifests = [mod.manifest for mod in self._modules.values()]
        
        # Если права не заданы (или это суперадмин с '*') - возвращаем все
        if user_permissions is None or "*" in user_permissions:
            return manifests

        filtered = []
        for m in manifests:
            # Проверяем, есть ли у пользователя хотя бы одно из прав модуля
            has_access = any(req in user_permissions for req in m.required_permissions)
            if has_access:
                filtered.append(m)
        return filtered


# Синглтон реестра
module_registry = ModuleRegistry()
