import inspect
import io

from destructify.parsing import ParsingContext, FieldContext
from destructify.structures.options import StructureOptions


class StructureBase(type):
    def __new__(cls, name, bases, namespace, **kwargs):
        # Ensure initialization is only performed for subclasses of Structure
        # (excluding Structure class itself).
        parents = [b for b in bases if isinstance(b, StructureBase)]
        if not parents:
            return super().__new__(cls, name, bases, namespace)

        # Create the class.
        module = namespace.pop('__module__')
        new_attrs = {'__module__': module}
        classcell = namespace.pop('__classcell__', None)
        if classcell is not None:
            new_attrs['__classcell__'] = classcell
        new_class = super().__new__(cls, name, bases, new_attrs, **kwargs)

        attr_meta = namespace.pop('Meta', None)
        meta = attr_meta or getattr(new_class, 'Meta', None)
        new_class.add_to_class('_meta', StructureOptions(meta))

        # Add all attributes to the class.
        for obj_name, obj in namespace.items():
            new_class.add_to_class(obj_name, obj)

        new_class._meta.initialize_fields()

        return new_class

    def __len__(cls):
        """Class method that allows you to do ``len(Structure)`` to retrieve the size of a :class:`Structure`."""
        return sum((len(f) for f in cls._meta.fields)) if hasattr(cls, '_meta') else 0

    def add_to_class(cls, name, value):
        # We should call the contribute_to_class method only if it's bound
        if not inspect.isclass(value) and hasattr(value, 'contribute_to_class'):
            value.contribute_to_class(cls, name)
        else:
            setattr(cls, name, value)


class Structure(metaclass=StructureBase):
    def __init__(self, **kwargs):
        """A base structure. It is the basis for all structures. You can pass in keyword arguments to provide
        different values than the field's defaults.

        :param kwargs:
        """
        context = ParsingContext(structure=self)
        for field in self._meta.fields:
            try:
                val = kwargs.pop(field.name)
            except KeyError:
                val = field.get_default(context)
            setattr(self, field.name, val)

        super().__init__()

    def __repr__(self):
        return '<%s: %s>' % (self.__class__.__name__, self)

    def __str__(self):
        values = []
        for field in self._meta.fields:
            values.append("%s=%r" % (field.name, getattr(self, field.name)))
        return '%s(%s)' % (self.__class__.__name__, ", ".join(values))

    def __eq__(self, other):
        if not isinstance(other, self.__class__) or not isinstance(self, other.__class__):
            return NotImplemented
        for field in self._meta.fields:
            if getattr(self, field.name) != getattr(other, field.name):
                return False
        return True

    def __bytes__(self):
        """Same as :meth:`to_bytes`, allowing you to use ``bytes(structure)``"""
        return self.to_bytes()

    def finalize(self, values):
        """Hook for hooking into the object just before it will be converted to binary data. This can be used to
        modify some values of the structure just before it is being written, e.g. for checksums.

        :param dict values: A dictionary of all values that are to be written to the stream.
        :return: The same dictionary, including modified values.
        """
        return values

    @classmethod
    def from_stream(cls, stream, context=None):
        """Reads a stream and converts it to a :class:`Structure` instance. You can explicitly provide a
        :class:`ParsingContext`, otherwise one will be created automatically.

        This will seek over the stream if one of the alignment options is set, e.g. :attr:`ParsingContext.alignment`
        or :attr:`Field.offset`. The return value in this case is the difference between the start offset of the stream
        and the offset of the highest read byte. In most cases, this will simply equal the amount of bytes consumed
        from the stream.

        :param stream: A buffered bytes stream.
        :param ParsingContext context: A context to use while parsing the stream.
        :rtype: Structure, int
        :return: A tuple of the constructed :class:`Structure` and the amount of bytes read (defined as the last
            position of the read bytes).
        """

        if context is None:
            context = ParsingContext()

        # We keep track of our starting offset, the current offset and the max offset.
        try:
            start_offset = max_offset = offset = stream.tell()
        except (OSError, AttributeError):
            start_offset = max_offset = offset = 0

        for field in cls._meta.fields:
            offset = field.seek_start(stream, context, offset)
            result, consumed = field.from_stream(stream, context)
            context.fields[field.name] = FieldContext(context, result,
                                                      parsed=True, start=offset, length=consumed, stream=stream)
            offset += consumed
            max_offset = max(offset, max_offset)

        return cls(**context.field_values), max_offset - start_offset

    def to_stream(self, stream, context=None):
        """Writes the current :class:`Structure` to the provided stream. You can explicitly provide a
        :class:`ParsingContext`, otherwise one will be created automatically.

        This will seek over the stream if one of the alignment options is set, e.g. :attr:`ParsingContext.alignment`
        or :attr:`Field.offset`. The return value in this case is the difference between the start offset of the stream
        and the offset of the highest written byte. In most cases, this will simply equal the amount of bytes written
        to the stream.

        :param stream: A buffered bytes stream.
        :param ParsingContext context: A context to use while writing the stream.
        :rtype: int
        :return: The number bytes written to the stream (defined as the maximum position of the bytes that were written)
        """
        if context is None:
            context = ParsingContext(structure=self)

        # done in two loops to allow for finalizing
        values = {}
        for field in self._meta.fields:
            values[field.name] = field.get_final_value(getattr(self, field.name), context)

        context.field_values = self.finalize(values)

        # We keep track of our starting offset, the current offset and the max offset.
        try:
            start_offset = max_offset = offset = stream.tell()
        except (OSError, AttributeError):
            start_offset = max_offset = offset = 0

        for field in self._meta.fields:
            value = context.fields[field.name].value
            offset = field.seek_start(stream, context, offset)
            written = field.to_stream(stream, value, context)
            context.fields[field.name] = FieldContext(context, value,
                                                      parsed=True, start=offset, length=written, stream=stream)
            offset += written
            max_offset = max(offset, max_offset)

        offset += context.finalize_stream(stream)
        max_offset = max(offset, max_offset)

        return max_offset - start_offset

    @classmethod
    def from_bytes(cls, bytes):
        """A short-hand method of calling :meth:`from_stream`, using bytes rather than a stream, and returns the
        constructed :class:`Structure` immediately.
        """

        return cls.from_stream(io.BytesIO(bytes))[0]

    def to_bytes(self):
        """A short-hand method of calling :meth:`to_stream`, writing to bytes rather than to a stream. It returns the
        constructed bytes immediately.
        """
        bytesio = io.BytesIO()
        self.to_stream(bytesio)
        return bytesio.getvalue()

    @classmethod
    def as_cstruct(cls):
        result = "struct {} {{\n".format(cls._meta.object_name)
        for field in cls._meta.fields:
            result += "   " + field.ctype + ";\n"
        result += "}"
        return result

