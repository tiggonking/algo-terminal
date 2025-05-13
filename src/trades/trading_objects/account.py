from dataclasses import dataclass, field
from globals.trading import TGL
import os.path


@dataclass
class Account:
    id: int
    alias: str
    ib_type: str
    ib_algo: str
    ib_platform: str
    ib_port: int
    ib_client_id: int
    strategy_allocations: dict  # a dict of {strategy_id: allocation}, with allocation between 0 and 1
    strategy_security_types: dict  # a dict of {strategy_id: [primary instrument, secondary instrument]}
    ignored_positions: list
    parent_account: str = None
    log = None
    directory = None
    exit_results: list = field(default_factory=list)
    entry_results: list = field(default_factory=list)
    runtime_errors: list = field(default_factory=list)
    last_nav_write = None  # tracks the last time NAV was recorded for this account.  None means no record.

    def __setstate__(self, state):
        # This method is called during unpickling to set the object's state
        # Variables added since pickle object creation are added here
        for k, v in state.items():
            vars(self)[k] = v

        self.initial_nav_write_complete = False  # reset each time the account object is loaded.

    def valid(self):
        if self.ib_type not in ['FUND ADVISORY', 'MANAGED', 'TRADING']:
            raise ValueError(f'INVALID IB ACCOUNT TYPE specified for {self.alias} in config file')
        if self.ib_type == 'FUND ADVISORY' and self.ib_client_id != 0:
            raise ValueError(f'FUND ADVISORY ACCOUNT {self.alias} must have IB CLIENT ID = 0')
        if self.ib_type == 'MANAGED' and not self.parent_account:
            raise ValueError(f'MANAGED ACCOUNT {self.alias} does not have PARENT FUND ADVISORY ACCOUNT specified in '
                             f'config file')
        if self.ib_platform not in ['TWS', 'IBG']:
            raise ValueError(f'INVALID IB PLATFORM specified for {self.alias} in config file ')
        if self.ib_algo not in ['DARKICE', '']:
            raise ValueError(f'UNHANDLED IB Algo type {self.ib_algo} specified for {self.alias} in config file ')
        if self.directory and not os.path.isdir(self.directory):
            raise NotADirectoryError(
                f'INVALID DIRECTORY {self.directory} specified for {self.alias} in config file')
        if (not self.ib_port
                or (self.ib_port < 49152 and self.ib_port not in [4001, 4002, 7496, 7497])
                or self.ib_port > 65535):
            raise ValueError(
                f'INVALID PORT {self.ib_port} specified for {self.alias}.  Port numbers must be:\n'
                f'4001 (IB Gateway Live)\n'
                f'4002 (IB Gateway Paper)\n'
                f'7496 (TWS Live)\n'
                f'7497 (TWS Paper)\n '
                f'or a number from 49152 to 65535.')
        for k, v in self.strategy_allocations.items():
            if v > 1 or v < 0:
                raise ValueError(f'INVALID PCT ALLOCATION ({v}) specified for strategy {k} in {self.alias} in '
                                 f'config file. Allocation must be entered as a fraction between 0 and 1.')

        for k, v in self.strategy_security_types.items():
            if [sec_type for sec_type in v if sec_type and sec_type not in TGL.valid_ib_security_types]:
                raise ValueError(f'INVALID SECURITY TYPES ({v}) specified for strategy {k} in account '
                                 f'{self.alias} in config file.')

        return True
