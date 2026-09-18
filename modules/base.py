"""
ReconcileHub - Base Reconciliation Module Contract
Стандартный интерфейс, который обязан реализовать каждый модуль сверки в системе.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class ModuleManifest(BaseModel):
    id: str                         # Уникальный идентификатор модуля, например 'bank_rrn'
    name: str                       # Человекочитаемое название: 'Сверка банковского эквайринга (RRN)'
    version: str                    # Семантическая версия: '1.4.0'
    description: str                # Краткое назначение сверки
    category: str                   # Категория: 'Acquiring', 'Payments', 'Banking', 'Fiscal'
    icon: str                       # Название иконки для UI: 'Building2', 'Receipt', 'CreditCard'
    author: str                     # Автор / ответственный бухгалтер
    status: str = "active"          # 'active', 'draft', 'deprecated'
    workspace: Optional[str] = None  # Ключ специализированного React workspace; None = только backend
    required_permissions: List[str] = Field(default_factory=list)
    available_permissions: List[str] = Field(default_factory=list)
    required_files: List[Dict[str, str]] = Field(default_factory=list)


class ValidationResult(BaseModel):
    is_valid: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    columns_found: Dict[str, List[str]] = Field(default_factory=dict)


class ReconSummary(BaseModel):
    total_records_a: int = 0
    total_records_b: int = 0
    total_sum_a: float = 0.0
    total_sum_b: float = 0.0
    matched_count: int = 0
    discrepancy_count: int = 0
    diff_sum: float = 0.0
    match_percentage: float = 0.0
    execution_time_ms: float = 0.0


class ReconResult(BaseModel):
    run_id: str
    module_id: str
    timestamp: str
    status: str                    # 'COMPLETED', 'FAILED', 'WARNING'
    summary: ReconSummary
    by_date: List[Dict[str, Any]] = Field(default_factory=list)
    by_category: List[Dict[str, Any]] = Field(default_factory=list)
    discrepancies: List[Dict[str, Any]] = Field(default_factory=list)
    custom_metrics: Dict[str, Any] = Field(default_factory=dict)


class BaseReconciliationModule(ABC):
    """
    Абстрактный базовый класс для всех сверок.
    Любая новая сверка от коллеги ОБЯЗАНА наследоваться от этого класса.
    """

    @property
    @abstractmethod
    def manifest(self) -> ModuleManifest:
        """Возвращает метаданные модуля"""
        pass

    @abstractmethod
    def validate_inputs(self, files: Dict[str, bytes], params: Dict[str, Any]) -> ValidationResult:
        """Проверяет входные файлы (наличие колонок, заголовков, расширения)"""
        pass

    @abstractmethod
    def run(self, files: Dict[str, bytes], params: Dict[str, Any]) -> ReconResult:
        """
        Запускает алгоритм сверки на Polars/Pandas.
        Возвращает стандартизированный результат ReconResult.
        """
        pass

    @abstractmethod
    def get_analytics(self, run_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Возвращает специализированную аналитику именно для этого типа сверки.
        Например, для RRN: распределение комиссий и терминалов;
        Для нового модуля: его собственные специализированные метрики;
        Для 1С: разрывы сальдо.
        """
        pass

    @abstractmethod
    def export(self, run_id: str, format: str = "xlsx") -> bytes:
        """Экспортирует результат сверки в Excel/CSV"""
        pass
