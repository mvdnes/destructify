import inspect
from functools import total_ordering

from destructify.exceptions import StreamExhaustedError, UnknownDependentFieldError, ImpossibleToCalculateLengthError, \
    MisalignedFieldError


class NOT_PROVIDED:
    pass


def _retrieve_property(context, var, special_case_str=True):
    """Retrieves a property:

    * If the property is callable, and has 0 parameters, it is called without arguments
    * If the property is callable, and has 0 parameters, it is called with argument context
    * If special_case_str=True and var is a str, context[var] is returned
    * Otherwise var is returned
    """
    if callable(var):
        if len(inspect.signature(var).parameters) == 0:
            return var()
        return var(context)
    elif special_case_str and isinstance(var, str):
        return context[var]
    else:
        return var


@total_ordering
class Field:
    # These track each time a Field instance is created. Used to retain order.
    creation_counter = 0

    _ctype = None

    def __init__(self, name=None, default=NOT_PROVIDED, override=NOT_PROVIDED):
        self.structure = None

        self.name = name
        self.default = default
        self.override = override

        self.creation_counter = Field.creation_counter
        Field.creation_counter += 1

    def __len__(self):
        raise ImpossibleToCalculateLengthError()

    def initialize(self):
        """Hook that is called after all fields on a structure are loaded, so some additional multi-field things can
        be arranged.
        """
        return

    def contribute_to_class(self, cls, name):
        """Register the field with the model class it belongs to."""

        self.name = name
        self.structure = cls

        cls._meta.add_field(self)

    def __eq__(self, other):
        # Needed for @total_ordering
        if isinstance(other, Field):
            return self.creation_counter == other.creation_counter
        return NotImplemented

    def __lt__(self, other):
        # This is needed because bisect does not take a comparison function.
        if isinstance(other, Field):
            return self.creation_counter < other.creation_counter
        return NotImplemented

    def __repr__(self):
        """Display the module, class, and name of the field."""
        path = '%s.%s' % (self.__class__.__module__, self.__class__.__qualname__)
        name = getattr(self, 'name', None)
        if name is not None:
            return '<%s: %s>' % (path, name)
        return '<%s>' % path

    @property
    def has_default(self):
        return self.default is not NOT_PROVIDED

    def get_default(self, context):
        if not self.has_default:
            return None
        return _retrieve_property(context, self.default, special_case_str=False)

    @property
    def has_override(self):
        return self.override is not NOT_PROVIDED

    def get_overridden_value(self, value, context):
        if not self.has_override:
            return value
        elif callable(self.override):
            return self.override(context, value)
        else:
            return self.override

    @property
    def ctype(self):
        ctype = self._ctype or self.__class__.__name__
        return "{} {}".format(ctype, self.name)

    def get_final_value(self, value, context=None):
        return self.get_overridden_value(value, context)

    def from_stream(self, stream, context=None):
        """Given a stream of bytes object, consumes  a given bytes object to Python representation.

        :param io.BufferedIOBase stream: The IO stream to consume from. The current position is set to the total of all
            previously parsed values.
        :param ParsingContext context: The context of this field.
        :returns: a tuple: the parsed value in its Python representation, and the amount of consumed bytes
        """
        raise NotImplementedError()

    def to_stream(self, stream, value, context=None):
        """Writes a value to the stream, and returns the amount of bytes written

        :param io.BufferedIOBase stream: The IO stream to write to.
        :param value: The value to write
        :param ParsingContext context: The context of this field.
        :returns: the amount of bytes written
        """

        return context.write_stream(stream, self.to_bytes(value))

    def to_bytes(self, value):
        """Method that converts a given Python representation to bytes. Default implementation assumes the value is
        already bytes.

        This value is a hook for :meth:`to_stream`.
        """
        return value


class ParsingContext:
    def __init__(self, *, structure=None, parsed_fields=None):
        self.structure = structure
        self.parsed_fields = parsed_fields
        self.bits_remaining = None

    def __getitem__(self, name):
        if self.structure and hasattr(self.structure, name):
            return getattr(self.structure, name)
        elif self.parsed_fields and name in self.parsed_fields:
            return self.parsed_fields[name]
        else:
            raise UnknownDependentFieldError("Dependent field %s is not loaded yet, so can't be used." % name)

    def __getattr__(self, name):
        """Allows you to do context.value instead of context['value']."""
        return self.__getitem__(name)

    def read_stream(self, stream, size=-1):
        """Alias for stream.read(size), but allows that to be hooked by the context.

        :return: the bytes read
        """
        if self.bits_remaining:
            raise MisalignedFieldError("A field following a BitField is misaligned. %s bits are still in the buffer"
                                       % len(self.bits_remaining))

        return stream.read(size)

    def write_stream(self, stream, value):
        return self._write_remaining_bits(stream) + stream.write(value)

    def finalize_stream(self, stream):
        return self._write_remaining_bits(stream)

    def read_stream_bits(self, stream, bit_count):
        result = []
        read_count = 0
        while len(result) < bit_count:
            # fill the bits_remaining as necessary
            if not self.bits_remaining:
                read = stream.read(1)
                read_count += 1
                if not read:
                    raise StreamExhaustedError("Could not parse bitfield, trying to read 1 byte")
                # trick to split each bit in a separate element
                self.bits_remaining = [read[0] >> i & 1 for i in range(7, -1, -1)]

            rem_size = bit_count - len(result)
            result.extend(self.bits_remaining[:rem_size])
            self.bits_remaining = self.bits_remaining[rem_size:]

        # this converts it back to a single integer
        return sum((result[i] << (len(result) - i - 1) for i in range(len(result)))), read_count

    def write_stream_bits(self, stream, value, bit_count, *, force_write=False):
        if not self.bits_remaining:
            self.bits_remaining = []
        self.bits_remaining.extend([value >> i & 1 for i in range(bit_count - 1, -1, -1)])

        if force_write:
            return self._write_remaining_bits(stream)
        return 0

    def _write_remaining_bits(self, stream):
        written = 0
        if self.bits_remaining:
            # we align to 8 bits
            self.bits_remaining.extend([0] * (8 - (len(self.bits_remaining) % 8)))

            number = sum((self.bits_remaining[i] << (len(self.bits_remaining) - i - 1)
                          for i in range(len(self.bits_remaining))))
            written = stream.write(number.to_bytes(len(self.bits_remaining) // 8, 'big'))
            self.bits_remaining = None

        return written