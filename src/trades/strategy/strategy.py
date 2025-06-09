from dataclasses import dataclass, field
from src.config.globals.log_setup import LOG


@dataclass
class Strategy:

    # this object can refer to a:
    #   STRATEGY - as imported from the config file, or
    #   STRATEGY-MODEL - as referenced in an RawOrder strategy_model_string

    qa_id: str
    qa_model: str
    direction: str
    todays_orders: list = field(default_factory=list)
    todays_successful_order_count: int = 0
    open_position_count: int = 0

    def __post_init__(self):
        self.qa_id = self.qa_id.upper()
        self.qa_model = self.qa_model.upper()
        self.direction = self.direction.upper()

    @property
    def qa_strategy_model(self):
        if self.qa_model:
            return f'{self.qa_id}_{self.qa_model}'
        else:
            return self.qa_id

    @property
    def entry_action(self):
        return 'BUY' if self.direction == 'LONG' else 'SELL'

    @property
    def exit_action(self):
        return 'SELL' if self.direction == 'LONG' else 'BUY'

    def valid(self):
        valid = True
        if self.direction not in ["LONG", "SHORT"]:
            LOG.error(f'INVALID DIRECTION specified for strategy {self.qa_strategy_model} in config file')
            valid = False
        return valid
