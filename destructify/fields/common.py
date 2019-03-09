import io

from . import Field
from .. import Substream, ParsingContext
from ..exceptions import DefinitionError, WriteError, WrongMagicError, StreamExhaustedError
from ..parsing.bitstream import BitStream
from .base import _retrieve_property


class BytesField(Field):
    def __init__(self, *args, length=None, terminator=None, step=1, terminator_handler='consume',
                 strict=True, padding=None, **kwargs):
        self.length = length
        self.terminator = terminator
        self.step = step
        self.terminator_handler = terminator_handler
        self.strict = strict
        self.padding = padding
        super().__init__(*args, **kwargs)

        if self.length is None and self.terminator is None:
            raise DefinitionError("The field {} must specify at least a length or terminator.".format(self.full_name))
        if self.length is None and self.padding is not None:
            raise DefinitionError("The field {} specifies padding, but not a length.".format(self.full_name))
        if self.terminator_handler not in ('consume', 'include', 'until'):
            raise DefinitionError("The field {} specifies '{}' as terminator handling, but that is invalid."
                                  .format(self.full_name, self.terminator_handler))
        if self.terminator_handler == 'until' and self.length is not None:
            raise DefinitionError("The field {} specifies 'until' as terminator handling, but also has a length."
                                  .format(self.full_name))

    def __len__(self):
        if isinstance(self.length, int):
            return self.length
        else:
            return super().__len__()

    @property
    def ctype(self):
        if self._ctype:
            return "{} {}".format(self._ctype, self.name)
        elif self.length is not None:
            return "{} {}[{}]".format(self.__class__.__name__, self.name, "" if callable(self.length) else self.length)
        else:
            return "{} {}[]".format(self.__class__.__name__, self.name)

    def initialize(self):
        """Overrides the content of the length field if possible."""

        if isinstance(self.length, str):
            related_field = self.bound_structure._meta.get_field_by_name(self.length)
            if not related_field.has_override:
                related_field.override = lambda s, v: len(s[self.name]) if v is None else v

    def get_length(self, context):
        return _retrieve_property(context, self.length)

    def to_python(self, value):
        """A hook that is called by :meth:`from_stream` to convert a given bytes object to a Python value.

        The default implementation is to return the value as-is, but subclasses may choose to override this instead of
        writing a custom :meth:`from_stream` method.
        """
        return value

    def from_python(self, value):
        """A hook that is called by :meth:`to_stream` to convert a given Python representation to bytes.

        The default implementation is to return the value as-is, but subclasses may choose to override this instead of
        writing a custom :meth:`to_stream` method.
        """
        return value

    def from_stream(self, stream, context):
        if self.length is None:
            return self._from_stream_terminated(stream, context)
        else:
            return self._from_stream_fixed_length(stream, context)

    def to_stream(self, stream, value, context):
        if self.length is None:
            return self._to_stream_terminated(stream, value, context)
        else:
            return self._to_stream_fixed_length(stream, value, context)

    def _from_stream_fixed_length(self, stream, context):
        length = self.get_length(context)
        read = stream.read(length)
        if len(read) < length and self.strict:
            raise StreamExhaustedError("Could not parse field %s, trying to read %s bytes, but only %s read." %
                                       (self.full_name, length, len(read)))

        # Remove padding or find the terminator
        if self.terminator is not None:
            value = b""
            for i in range(0, len(read), self.step):
                c = read[i:i+self.step]
                value += c
                if len(c) == self.step and value.endswith(self.terminator):
                    # We can expect the consume and include handlers here.
                    if self.terminator_handler == 'consume':
                        value = value[:-len(self.terminator)]
                    break
            else:
                if self.strict:
                    raise StreamExhaustedError("Could not parse field %s; did not find terminator %s" %
                                               (self.name, self.terminator))

        elif self.padding is not None:
            value = read
            while value[-len(self.padding):] == self.padding:
                value = value[:-len(self.padding)]

        else:
            value = read

        return self.to_python(value), len(read)

    def _to_stream_fixed_length(self, stream, value, context):
        length = self.get_length(context)

        val = self.from_python(value)
        if self.terminator is not None:
            # We can expect the consume and include handlers here.
            if self.terminator_handler == 'consume':
                val += self.terminator
            elif self.terminator_handler == 'include' and not val.endswith(self.terminator) and self.strict:
                raise WriteError("The field {} does not include its terminator.".format(self.full_name))

        if length < 0:
            # For negative lengths, we just write to the stream
            return stream.write(val)

        if len(val) < length:
            if self.padding is not None:
                remaining = length - len(val)

                if self.strict and remaining % len(self.padding) != 0:
                    raise WriteError("The field %s must be padded, but the remaining bytes %d are not a multiple of %d." %
                                     (self.full_name, remaining, len(self.padding)))

                # slicing for paddings longer than 1 byte
                val = (val + self.padding * remaining)[:length]
            elif self.strict:
                raise WriteError("The contents of %s are %d long, but expecting %d." %
                                 (self.full_name, len(val), length))
        elif len(val) > length:
            if self.strict:
                raise WriteError("The contents of %s are %d long, but expecting %d." %
                                 (self.full_name, len(val), length))

            val = val[:length]

        return stream.write(val)

    def _from_stream_terminated(self, stream, context):
        read = b""
        while True:
            if self.terminator_handler == 'until' and hasattr(stream, 'peek') and len(self.terminator) <= self.step:
                # Optimize if we have peek available, so we don't have to seek back
                # If the terminator is shorter than the step, we don't use peek, as we have to seek back anyway
                if (stream.peek(self.step)).endswith(self.terminator):
                    if len(self.terminator) < self.step:
                        # we need to consume until the terminator.
                        read += stream.read(self.step - len(self.terminator))
                    return self.to_python(read), len(read)

            c = stream.read(self.step)
            read += c
            if len(c) != self.step:
                if self.strict:
                    raise StreamExhaustedError("Could not parse field %s; did not find terminator %s" %
                                               (self.name, self.terminator))
                else:
                    return self.to_python(read), len(read)

            if read.endswith(self.terminator):
                if self.terminator_handler == 'consume':
                    return self.to_python(read[:-len(self.terminator)]), len(read)
                elif self.terminator_handler == 'include':
                    return self.to_python(read), len(read)
                elif self.terminator_handler == 'until' \
                        and not (hasattr(stream, 'peek') and len(self.terminator) <= self.step):
                    read = read[:-len(self.terminator)]
                    stream.seek(-len(self.terminator), io.SEEK_CUR)
                    return self.to_python(read), len(read)

    def _to_stream_terminated(self, stream, value, context):
        val = self.from_python(value)
        if self.terminator_handler == 'consume':
            return stream.write(val + self.terminator)
        elif self.terminator_handler == 'include':
            if not val.endswith(self.terminator) and self.strict:
                raise WriteError("The field {} does not include its terminator.".format(self.full_name))
            return stream.write(val)
        elif self.terminator_handler == 'until':
            return stream.write(val)


class FixedLengthField(BytesField):
    def __init__(self, length, *args, **kwargs):
        super().__init__(length=length, *args, **kwargs)


class TerminatedField(BytesField):
    def __init__(self, terminator=b'\0', *args, **kwargs):
        super().__init__(*args, terminator=terminator, **kwargs)


class BitField(FixedLengthField):
    def __init__(self, length, *args, realign=False, **kwargs):
        self.realign = realign
        super().__init__(length, *args, **kwargs)

    def __len__(self):
        if isinstance(self.length, int):
            return self.length / 8
        else:
            return super().__len__()

    @property
    def ctype(self):
        if self._ctype:
            return "{} {}".format(self._ctype, self.name)
        else:
            return "{} {}[{}]".format(self.__class__.__name__, self.name,
                                      "" if callable(self.length) else "{} bits".format(self.length))

    def initialize(self):
        """Overrides the content of the length field if possible."""

        if isinstance(self.length, str):
            related_field = self.bound_structure._meta.get_field_by_name(self.length)
            if not related_field.has_override:
                related_field.override = lambda s, v: s[self.name].bit_length() if v is None else v

    def from_stream(self, stream: BitStream, context):
        result = stream.read_bits(self.get_length(context))
        if self.realign:
            stream.discard_bits()
        return result

    def to_stream(self, stream: BitStream, value, context):
        result = stream.write_bits(value, self.get_length(context))
        if self.realign:
            result += stream.finalize()
        return result

    def seek_start(self, stream, context, position):
        if self.offset is not None or self.skip is not None:
            # allow offset and skip to work as normal
            return super().seek_start(stream, context, position)
        elif self.bound_structure is not None and self.bound_structure._meta.alignment is not None:
            # check if we allow the alignment to apply to this field: this is the case if the previous field is not
            # of BitField
            prev_field = self.bound_structure._meta.get_previous_field(self)
            if not isinstance(prev_field, BitField) or prev_field.realign:
                return super().seek_start(stream, context, position)

        try:
            return stream.tell()
        except (OSError, AttributeError):
            return position


class StringField(BytesField):
    def __init__(self, *args, encoding=None, errors='strict', **kwargs):
        self.encoding = encoding
        self.errors = errors
        super().__init__(*args, **kwargs)

    def to_python(self, value):
        return super().to_python(value).decode(self.encoding, self.errors)

    def from_python(self, value):
        return super().from_python(value.encode(self.encoding, self.errors))

    def contribute_to_class(self, cls, name):
        super().contribute_to_class(cls, name)

        # If byte_order is specified in the meta of the structure, we change our own default byte order (if not set)
        if self.bound_structure._meta.encoding and not self.encoding:
            self.encoding = self.bound_structure._meta.encoding

        if self.encoding is None:
            raise DefinitionError("No encoding for %s provided" % self.full_name)


class IntegerField(FixedLengthField):
    def __init__(self, length, byte_order=None, *args, signed=False, **kwargs):
        self.byte_order = byte_order
        self.signed = signed
        super().__init__(length=length, *args, **kwargs)

    def to_python(self, value):
        val = super().to_python(value)
        return int.from_bytes(val,
                              byteorder='big' if not self.byte_order and len(val) == 1 else self.byte_order,
                              signed=self.signed)

    def to_stream(self, stream, value, context):
        # We can't use from_python here as we need the field's length.
        length = self.get_length(context)
        val = self.from_python(value.to_bytes(length,
                                              byteorder='big' if not self.byte_order and length == 1 else self.byte_order,
                                              signed=self.signed))
        return stream.write(val)

    def contribute_to_class(self, cls, name):
        super().contribute_to_class(cls, name)

        # If byte_order is specified in the meta of the structure, we change our own default byte order (if not set)
        if self.bound_structure._meta.byte_order and not self.byte_order:
            self.byte_order = self.bound_structure._meta.byte_order

        if self.byte_order is None:
            if not isinstance(self.length, int) or not self.length == 1:
                raise DefinitionError("No byte_order for %s provided" % self.full_name)


class VariableLengthQuantityField(Field):
    def from_stream(self, stream, context):
        result = 0
        count = 0
        while True:
            c = stream.read(1)
            count += 1
            if len(c) != 1:
                raise StreamExhaustedError("Could not read 1 byte while parsing field {}".format(self.full_name))
            c = c[0]  # get integer value

            result <<= 7
            result += c & 0x7f
            if not c & 0x80:
                break
        return result, count

    def to_stream(self, stream, value, context):
        if value < 0:
            raise OverflowError()

        result = [value & 0x7f]
        value >>= 7
        while value > 0:
            result.insert(0, value & 0x7f | 0x80)
            value >>= 7
        return stream.write(bytes(result))


class StructureField(Field):
    def __init__(self, structure, *args, length=None, **kwargs):
        self.structure = structure
        self.length = length

        super().__init__(*args, **kwargs)

        if not self.has_default:
            self.default = lambda: self.structure()

    def __len__(self):
        if isinstance(self.length, int):
            return self.length
        else:
            return len(self.structure)

    @property
    def ctype(self):
        ctype = self._ctype or self.structure._meta.object_name
        return "{} {}".format(ctype, self.name)

    def get_length(self, context):
        return _retrieve_property(context, self.length)

    def from_stream(self, stream, context):
        length = None
        if self.length is not None:
            length = self.get_length(context)

        with Substream(stream,
                       start=stream.tell(),
                       stop=stream.tell() + length if length is not None else None) as substream:
            res, consumed = self.structure.from_stream(substream, context=ParsingContext(parent=context))

        if length is not None and consumed < length:
            stream.seek(length - consumed, io.SEEK_CUR)
            consumed = length
        return res, consumed

    def to_stream(self, stream, value, context):
        if value is None:
            value = self.structure()
        # TODO: respect length
        return value.to_stream(stream)
