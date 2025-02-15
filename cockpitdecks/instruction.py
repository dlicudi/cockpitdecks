# Base classes for interface with the simulation software
#
from __future__ import annotations
import threading
import logging
from abc import ABC, abstractmethod

from cockpitdecks import CONFIG_KW
from .strvar import Formula

logger = logging.getLogger(__name__)
# logger.setLevel(SPAM_LEVEL)  # To see when simulator_variable are updated
# logger.setLevel(logging.DEBUG)


class InstructionFactory:
    """An InstructionFactory is an entity capable of generating instructions
    Often, the entity generates instruction it will perform.
    """

    def instruction_factory(self, **kwargs) -> Instruction:
        raise NotImplementedError("Please implement InstructionFactory.instruction_factory method")


class Instruction(ABC):
    """An Instruction to execute an action by a Performer.
    Often, the Performer is an InstructionFactory and generates the Instruction it will later execute.
    """

    INSTRUCTION_NAME = "undefined"

    def __init__(self, name: str, **kwargs) -> None:
        self.name = name
        self.performer = kwargs.get("performer")
        self.delay = kwargs.get("delay", 0)
        self.condition = kwargs.get("condition")
        self._timer: threading.Timer | None = None

        if self.delay is None:
            self.delay = 0

        if self.condition is not None:
            if "${" in self.condition:
                self._condition = Formula(owner=self.performer, formula=self.condition)
            else:  # we assume the confition is a single dataref, we enclose it in ${} to make it a formula
                self._condition = Formula(owner=self.performer, formula=f"${{{self.condition}}}")

    @classmethod
    def name(cls) -> str:
        return cls.INSTRUCTION_NAME

    def __str__(self) -> str:
        return f"{self.INSTRUCTION_NAME} {self.name}"

    @staticmethod
    def all_subclasses(cls) -> list:
        """Returns the list of all subclasses.

        Recurses through all sub-sub classes

        Returns:
            [list]: list of all subclasses

        Raises:
            ValueError: If invalid class found in recursion (types, etc.)
        """
        if cls is type:
            raise ValueError("Invalid class - 'type' is not a class")
        subclasses = set()
        stack = []
        try:
            stack.extend(cls.__subclasses__())
        except (TypeError, AttributeError) as ex:
            raise ValueError("Invalid class" + repr(cls)) from ex
        while stack:
            sub = stack.pop()
            subclasses.add(sub)
            try:
                stack.extend(s for s in sub.__subclasses__() if s not in subclasses)
            except (TypeError, AttributeError):
                continue
        return list(subclasses)

    @abstractmethod
    def _execute(self):
        if self.performer is not None and hasattr(self.performer, "execute"):
            self.performer.execute(instruction=self)
        self.clean_timer()

    @abstractmethod
    def _check_condition(self) -> bool:
        return True

    def clean_timer(self):
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def execute(self):
        if not self._check_condition():
            logger.debug(f"{self.name} not allowed to run")
            return
        if self._timer is None and self.delay > 0:
            self._timer = threading.Timer(self.delay, self._execute)
            self._timer.start()
            logger.debug(f"{self.name} will be executed in {self.delay} secs")
            return
        self._execute()


class MacroInstruction(Instruction):
    """A Macro Instruction is a collection of individual Instruction.
    Each instruction comes with its condition for execution and delay since activation.
    (Could have been called Instructions (plural form))
    """

    INSTRUCTION_NAME = "macro"

    def __init__(self, name: str, instructions: dict, **kwargs):
        Instruction.__init__(self, name=name, **kwargs)
        self.instructions = instructions
        self._instructions = []
        self.init()

    def __str__(self) -> str:
        return f"{super()} ({', '.join([c.name for c in self._instructions])})"

    def init(self):
        total_delay = 0
        count = 0
        if self.performer is not None:
            for c in self.instructions:
                total_delay = total_delay + c.get(CONFIG_KW.DELAY.value, 0)
                if total_delay > 0:
                    c[CONFIG_KW.DELAY.value] = total_delay
                ci = self.performer.instruction_factory(name=c[CONFIG_KW.COMMAND.value], **c)
                self._instructions.append(ci)
                count = count + 1
        else:
            logger.warning(f"{self.name} has no performer")

    def _check_condition(self):
        # condition checked in each individual instruction
        return True

    def _execute(self):
        for instruction in self._instructions:
            instruction.execute()


class NoOperation(Instruction):

    INSTRUCTION_NAME = "no-op"

    def __init__(self, **kwargs):
        name = kwargs.get(CONFIG_KW.NAME.value)
        if name is None:
            name = self.INSTRUCTION_NAME
        else:
            del kwargs[CONFIG_KW.NAME.value]
        Instruction.__init__(self, name=name, kwargs=kwargs)

    def _check_condition(self):
        # condition checked in each individual instruction
        return True

    def _execute(self):
        logger.warning(f"{self.name} born to do nothing")
