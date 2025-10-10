from abc import ABC, abstractmethod
import numbers
from typing import List, Union, Dict, TypeVar, Tuple

from yfinance.const import EQUITY_SCREENER_EQ_MAP, EQUITY_SCREENER_FIELDS
from yfinance.const import FUND_SCREENER_EQ_MAP, FUND_SCREENER_FIELDS
from yfinance.exceptions import YFNotImplementedError
from ..utils import dynamic_docstring, generate_list_table_from_dict_universal

T = TypeVar('T', bound=Union[str, numbers.Real])

class QueryBase(ABC):
    def __init__(self, operator: str, operand: Union[ List['QueryBase'], Tuple[str, Tuple[Union[str, numbers.Real],  ...]] ]):
        operator = operator.upper()

        if not isinstance(operand, list):
            raise TypeError('Invalid operand type')
        if len(operand) <= 0:
            raise ValueError('Invalid field for EquityQuery')
            
        if operator == 'IS-IN':
            self._validate_isin_operand(operand)
        elif operator in {'OR','AND'}: 
            self._validate_or_and_operand(operand)
        elif operator == 'EQ': 
            self._validate_eq_operand(operand)
        elif operator == 'BTWN': 
            self._validate_btwn_operand(operand)
        elif operator in {'GT','LT','GTE','LTE'}: 
            self._validate_gt_lt(operand)
        else: 
            raise ValueError('Invalid Operator Value')

        self.operator = operator
        self.operands = operand

    @property
    @abstractmethod
    def valid_fields(self) -> List:
        raise YFNotImplementedError('valid_fields() needs to be implemented by child')

    @property
    @abstractmethod
    def valid_values(self) -> Dict:
        raise YFNotImplementedError('valid_values() needs to be implemented by child')

    def _validate_or_and_operand(self, operand: List['QueryBase']) -> None:
        if len(operand) <= 1: 
            raise ValueError('Operand must be length longer than 1')
        if all(isinstance(e, QueryBase) for e in operand) is False: 
            raise TypeError(f'Operand must be type {type(self)} for OR/AND')

    def _validate_eq_operand(self, operand: List[Union[str, numbers.Real]]) -> None:
        if len(operand) != 2:
            raise ValueError('Operand must be length 2 for EQ')
        
        if  not any(operand[0] in fields_by_type for fields_by_type in self.valid_fields.values()):
            raise ValueError(f'Invalid field for {type(self)} "{operand[0]}"')
        if operand[0] in self.valid_values:
            vv = self.valid_values[operand[0]]
            if isinstance(vv, dict):
                # this data structure is slightly different to generate better docs, 
                # need to unpack here.
                vv = set().union(*[e for e in vv.values()])
            if operand[1] not in vv:
                raise ValueError(f'Invalid EQ value "{operand[1]}"')
    
    def _validate_btwn_operand(self, operand: List[Union[str, numbers.Real]]) -> None:
        if len(operand) != 3: 
            raise ValueError('Operand must be length 3 for BTWN')
        if  not any(operand[0] in fields_by_type for fields_by_type in self.valid_fields.values()):
            raise ValueError(f'Invalid field for {type(self)}')
        if isinstance(operand[1], numbers.Real) is False:
            raise TypeError('Invalid comparison type for BTWN')
        if isinstance(operand[2], numbers.Real) is False:
            raise TypeError('Invalid comparison type for BTWN')

    def _validate_gt_lt(self, operand: List[Union[str, numbers.Real]]) -> None:
        if len(operand) != 2:
            raise ValueError('Operand must be length 2 for GT/LT')
        if  not any(operand[0] in fields_by_type for fields_by_type in self.valid_fields.values()):
            raise ValueError(f'Invalid field for {type(self)} "{operand[0]}"')
        if isinstance(operand[1], numbers.Real) is False:
            raise TypeError('Invalid comparison type for GT/LT')

    def _validate_isin_operand(self, operand: List['QueryBase']) -> None:
        if len(operand) < 2:
            raise ValueError('Operand must be length 2+ for IS-IN')
        
        if  not any(operand[0] in fields_by_type for fields_by_type in self.valid_fields.values()):
            raise ValueError(f'Invalid field for {type(self)} "{operand[0]}"')
        if operand[0] in self.valid_values:
            vv = self.valid_values[operand[0]]
            if isinstance(vv, dict):
                # this data structure is slightly different to generate better docs, 
                # need to unpack here.
                vv = set().union(*[e for e in vv.values()])
            for i in range(1, len(operand)):
                if operand[i] not in vv:
                    raise ValueError(f'Invalid EQ value "{operand[i]}"')

    def to_dict(self) -> Dict:
        op = self.operator
        ops = self.operands
        if self.operator == 'IS-IN':
            # Expand to OR of EQ queries
            op = 'OR'
            ops = [type(self)('EQ', [self.operands[0], v]) for v in self.operands[1:]]
        return {
            "operator": op,
            "operands": [o.to_dict() if isinstance(o, QueryBase) else o for o in ops]
        }

    def __repr__(self, indent=0) -> str:
        indent_str = "  " * indent
        class_name = self.__class__.__name__

        if isinstance(self.operands, list):
            # For list operands, check if they contain any QueryBase objects
            if any(isinstance(op, QueryBase) for op in self.operands):
                # If there are nested queries, format them with newlines
                operands_str = ",\n".join(
                    f"{indent_str}  {op.__repr__(indent + 1) if isinstance(op, QueryBase) else repr(op)}"
                    for op in self.operands
                )
                return f"{class_name}({self.operator}, [\n{operands_str}\n{indent_str}])"
            else:
                # For lists of simple types, keep them on one line
                return f"{class_name}({self.operator}, {repr(self.operands)})"
        else:
            # Handle single operand
            return f"{class_name}({self.operator}, {repr(self.operands)})"

    def __str__(self) -> str:
        return self.__repr__()


class EquityQuery(QueryBase):
    """
    The `EquityQuery` class constructs filters for stocks based on specific criteria such as region, sector, exchange, and peer group.

    Start with value operations: `EQ` (equals), `IS-IN` (is in), `BTWN` (between), `GT` (greater than), `LT` (less than), `GTE` (greater or equal), `LTE` (less or equal).

    Combine them with logical operations: `AND`, `OR`.

    Example:
        Predefined Yahoo query `aggressive_small_caps`:
        
        .. code-block:: python

            from yfinance import EquityQuery

            EquityQuery('and', [
                EquityQuery('is-in', ['exchange', 'NMS', 'NYQ']), 
                EquityQuery('lt', ["epsgrowth.lasttwelvemonths", 15])
            ])
    """

    @dynamic_docstring({"valid_operand_fields_table": generate_list_table_from_dict_universal(EQUITY_SCREENER_FIELDS)})
    @property
    def valid_fields(self) -> Dict:
        """
        Valid operands, grouped by category.
        {valid_operand_fields_table}
        """
        return EQUITY_SCREENER_FIELDS
    
    @dynamic_docstring({"valid_values_table": generate_list_table_from_dict_universal(EQUITY_SCREENER_EQ_MAP, concat_keys=['exchange', 'industry'])})
    @property
    def valid_values(self) -> Dict:
        """
        Most operands take number values, but some have a restricted set of valid values.
        {valid_values_table}
        """
        return EQUITY_SCREENER_EQ_MAP


class FundQuery(QueryBase):
    """
    The `FundQuery` class constructs filters for mutual funds based on specific criteria such as region, sector, exchange, and peer group.

    Start with value operations: `EQ` (equals), `IS-IN` (is in), `BTWN` (between), `GT` (greater than), `LT` (less than), `GTE` (greater or equal), `LTE` (less or equal).

    Combine them with logical operations: `AND`, `OR`.

    Example:
        Predefined Yahoo query `solid_large_growth_funds`:
        
        .. code-block:: python

            from yfinance import FundQuery
            
            FundQuery('and', [
                FundQuery('eq', ['categoryname', 'Large Growth']), 
                FundQuery('is-in', ['performanceratingoverall', 4, 5]), 
                FundQuery('lt', ['initialinvestment', 100001]), 
                FundQuery('lt', ['annualreturnnavy1categoryrank', 50]), 
                FundQuery('eq', ['exchange', 'NAS'])
            ])
    """
    @dynamic_docstring({"valid_operand_fields_table": generate_list_table_from_dict_universal(FUND_SCREENER_FIELDS)})
    @property
    def valid_fields(self) -> Dict:
        """
        Valid operands, grouped by category.
        {valid_operand_fields_table}
        """
        return FUND_SCREENER_FIELDS
    
    @dynamic_docstring({"valid_values_table": generate_list_table_from_dict_universal(FUND_SCREENER_EQ_MAP)})
    @property
    def valid_values(self) -> Dict:
        """
        Most operands take number values, but some have a restricted set of valid values.
        {valid_values_table}
        """
        return FUND_SCREENER_EQ_MAP

