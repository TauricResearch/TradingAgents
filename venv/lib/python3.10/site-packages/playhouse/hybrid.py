from peewee import ModelDescriptor


# Hybrid methods/attributes, based on similar functionality in SQLAlchemy:
# http://docs.sqlalchemy.org/en/improve_toc/orm/extensions/hybrid.html
class hybrid_method(ModelDescriptor):
    def __init__(self, func, expr=None):
        self.func = func
        self.expr = expr or func

    def __get__(self, instance, instance_type):
        if instance is None:
            return self.expr.__get__(instance_type, instance_type.__class__)
        return self.func.__get__(instance, instance_type)

    def expression(self, expr):
        self.expr = expr
        return self


class hybrid_property(ModelDescriptor):
    def __init__(self, fget, fset=None, fdel=None, expr=None):
        self.fget = fget
        self.fset = fset
        self.fdel = fdel
        self.expr = expr or fget

    def __get__(self, instance, instance_type):
        if instance is None:
            return self.expr(instance_type)
        return self.fget(instance)

    def __set__(self, instance, value):
        if self.fset is None:
            raise AttributeError('Cannot set attribute.')
        self.fset(instance, value)

    def __delete__(self, instance):
        if self.fdel is None:
            raise AttributeError('Cannot delete attribute.')
        self.fdel(instance)

    def setter(self, fset):
        self.fset = fset
        return self

    def deleter(self, fdel):
        self.fdel = fdel
        return self

    def expression(self, expr):
        self.expr = expr
        return self
