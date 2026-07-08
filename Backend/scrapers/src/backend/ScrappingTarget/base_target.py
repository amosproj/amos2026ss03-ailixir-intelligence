from abc import ABCMeta, abstractmethod


class BaseTarget(metaclass=ABCMeta):
    @abstractmethod
    def get_all_new_target_elements(self) -> []:
        pass

    def to_dict(self):
        return self.__dict__

    def __repr__(self):
        attributes = ', '.join(f'{key}={value!r}' for key, value in self.__dict__.items())
        return f'<{self.__class__.__name__} {attributes}>'
