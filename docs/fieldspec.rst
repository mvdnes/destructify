.. _FieldSpec:

=============================
Built-in fields specification
=============================
.. module:: destructify

Destructify comes with a smorgasbord of built-in field types. This means that you can specify the most common structures
right out of the box.

Common attributes
=================
All fields are subclasses of :class:`Field` and therefore come with some properties by default. These are the following
and can be defined on every class:

.. attribute:: Field.name

  The field name. This is set automatically by the :class:`Structure`'s metaclass when it is initialized.

.. attribute:: Field.default

   The field's default value. This is used when the :class:`Structure` is initialized if it is provided. If it is not
   provided, the field determines its own default value.

   You can set it to one of the following:

   * A callable with zero arguments
   * A callable taking a :class:`ParsingContext` object
   * A value

   All of the following are valid usages of the default attribute::

       Field(default=None)
       Field(default=3)
       Field(default=lambda: datetime.datetime.now())
       Field(default=lambda c: c.value)

   You can check whether a default is set using the :attr:`Field.has_default` attribute. The default given a context is
   obtained by calling ``Field.get_default(context)``

.. attribute:: Field.override

   Using :attr:`Field.override`, you can change the value of the field in a structure, just before it is being written to a
   stream. This is useful if you, for instance, wish to override a field's value based on some other property in the
   structure. For instance, you can change a length field based on the actual length of a field.

   You can set it to one of the following:

   * A value
   * A callable taking a :class:`ParsingContext` object and the current value of the field

   For instance::

       Field(override=3)
       Field(override=lambda c, v: c.value if v is None else v)

   You can check whether an override is set using the :attr:`Field.has_override` attribute. The override given a context is
   obtained by calling ``Field.get_overridden_value(value, context)``. Note, however, that you probably want to call
   :meth:`Field.get_final_value` instead.

MagicField
==========
.. autoclass:: MagicField

   The :class:`MagicField` is intended to read/write a specific magic string from and to a stream. If anything else is
   read or written, an exception is raised. Note that the :attr:`Field.default` is also set to the magic.

   .. attribute:: magic

      The magic bytes that must be checked against.

BytesField
==========
.. autoclass:: BytesField

   A :class:`BytesField` can be used to read bytes from a stream. This is most commonly used as a base class for other
   methods, as it can be used for the most common use cases.

   There are three typical ways to use this field:

   * Setting a :attr:`BytesField.length` to read a specified amount of bytes from a stream.
   * Setting a :attr:`BytesField.terminator` to read until the specified byte from a stream.
   * Setting both  :attr:`BytesField.length` and :attr:`BytesField.terminator` to first read the specified amount of
     bytes from a stream and then find the terminator in this amount of bytes.

   .. attribute:: BytesField.length

      This specifies the length of the field. This is the amount of data that is read from the stream and written to
      the stream. The length may also be negative to indicate an unbounded read, i.e. until the end of stream.

      You can set this attribute to one of the following:

      * A callable with zero arguments
      * A callable taking a :class:`ParsingContext` object
      * A string that represents the field name that contains the length
      * An integer

      For instance::

          class StructureWithLength(Structure):
              length = UnsignedByteField()
              value = BytesField(length='length')

      The length given a context is obtained by calling ``FixedLengthField.get_length(value, context)``.

   When the class is initialized on a :class:`Structure`, and the length property is specified using a string, the
   default implementation of the :attr:`Field.override` on the named attribute of the :class:`Structure` is changed
   to match the length of the value in this :class:`Field`.

   Continuing the above example, the following works automatically::

       >>> bytes(StructureWithLength(value=b"123456"))
       b'\x06123456'

   However, explicitly specifying the length would override this::

       >>> bytes(StructureWithLength(length=1, value=b"123456"))
       b'\x01123456'

   This behaviour can be changed by manually specifying a different :attr:`Field.override` on ``length``.

   .. attribute:: BytesField.strict

      This boolean (defaults to :const:`True`) enables raising errors in the following cases:

      * A :class:`StreamExhaustedError` when there are not sufficient bytes to completely fill the field while reading.
      * A :class:`StreamExhaustedError` when the terminator is not found while reading.
      * A :class:`WriteError` when there are not sufficient bytes to fill the field while writing and
        :attr:`padding` is not set.
      * A :class:`WriteError` when the field must be padded, but the bytes that are to be written are not a multiple of
        the size of :attr:`padding`.
      * A :class:`WriteError` when there are too many bytes to fit in the field while writing.

      Disabling :attr:`FixedLengthField.strict` is not recommended, as this may cause inadvertent errors.

   .. attribute:: BytesField.padding

      When set, this value is used to pad the bytes to fill the entire field while writing, and chop this off the
      value while reading. Padding is removed right to left and must be aligned to the end of the value (which matters
      for multibyte paddings).

      While writing in :attr:`strict` mode, and the remaining bytes are not a multiple of the length of this value,
      a :class:`WriteError` is raised. If :attr:`strict` mode is not enabled, the padding will simply be appended to the
      value and chopped of whenever required. However, this can't be parsed back by Destructify (as the padding is not
      aligned to the end of the structure).

      This can only be set when :attr:`length` is used.

   .. attribute:: BytesField.terminator

      The terminator to read until. It can be multiple bytes.

      When this is set, :attr:`padding` is ignored while reading from a stream, but may be used to pad bytes that are
      written.

   .. attribute:: BytesField.step

      The size of the steps for finding the terminator. This is useful if you have a multi-byte terminator that is
      aligned. For instance, when reading NULL-terminated UTF-16 strings, you'd expect two NULL bytes aligned to two
      bytes (from the start). Defaults to 1.

      Example usage::

          >>> class TerminatedStructure(Structure):
          ...     foo = BytesField(terminator=b'\0')
          ...     bar = BytesField(terminator=b'\r\n')
          ...
          >>> TerminatedStructure.from_bytes(b"hello\0world\r\n")
          <TerminatedStructure: TerminatedStructure(foo=b'hello', bar=b'world')>

   This class can be used trivially to extend functionality. For instance, :class:`StringField` is a subclass of this
   field. To aid subclassing, two additional hooks are provided:

   .. automethod:: BytesField.from_python

   .. automethod:: BytesField.to_python

FixedLengthField
----------------
.. autoclass:: FixedLengthField

   This class is identical to :class:`BytesField`, but specifies the length as a required first argument. It is intended
   to read a fixed amount of :attr:`BytesField.length` bytes.

TerminatedField
---------------
.. autoclass:: TerminatedField

   This class is identical to :class:`BytesField`, but specifies the terminator as its first argument, defaulting
   to a single NULL-byte. It is intended to continue reading until :attr:`BytesField.terminator` is hit.

StringField
===========

.. autoclass:: StringField

   The :class:`StringField` is a subclass of :class:`BytesField` that converts the resulting :class:`bytes` object to a
   :class:`str` object, given the :attr:`encoding` and :attr:`errors` attributes.

   See :class:`BytesField` for all available attributes.

   .. attribute:: StringField.encoding

      The encoding of the string. Defaults to ``utf-8``, but can be any encoding supported by Python.

   .. attribute:: StringField.errors

      The error handler for encoding/decoding failures. Defaults to Python's default of ``strict``.

IntegerField
============
.. autoclass:: IntegerField

   The :class:`IntegerField` is used for fixed-length representations of integers.

   .. note::

      The :class:`IntegerField` is not to be confused with the :class:`IntField`, which is based on :class:`StructField`.

   .. attribute:: IntegerField.length

      The length (in bytes) of the field. When writing a number that is too large to be held in this field, you will
      get an ``OverflowError``.

   .. attribute:: IntegerField.byte_order

      The byte order (i.e. endianness) of the bytes in this field. If you do not specify this, you must specify a
      ``byte_order`` on the structure.

   .. attribute:: IntegerField.signed

      Boolean indicating whether the integer is to be interpreted as a signed or unsigned integer.

VariableLengthQuantityField
===========================
.. autoclass:: VariableLengthQuantityField

   Implementation of a `variable-length quantity <https://en.wikipedia.org/wiki/Variable-length_quantity>`_ structure.

BitField
========

.. autoclass:: BitField

   A subclass of :class:`FixedLengthField`, reading bits rather than bytes. The field writes and reads integers.

   When using the :class:`BitField`, you must be careful to align the field to whole bytes. You can use multiple
   :class:`BitField` s consecutively without any problem, but the following would raise errors::

       class MultipleBitFields(Structure):
           bit0 = BitField(length=1)
           bit1 = BitField(length=1)
           byte = FixedLengthField(length=1)

   You can fix this by ensuring all consecutive bit fields align to a byte in total, or, alternatively, you can specify
   :attr:`realign` on the last :class:`BitField` to realign to the next byte.

   .. attribute:: BitField.length

      The amount of bits to read.

   .. attribute:: BitField.realign

      This specifies whether the stream must be realigned to entire bytes after this field. If set, after bits have
      been read, bits are skipped until the next whole byte. This means that the intermediate bits are ignored. When
      writing and this boolean is set, it is padded with zero-bits until the next byte boundary.

      Note that this means that the following::

           class BitStructure(Structure):
               foo = BitField(length=5, realign=True)
               bar = FixedLengthField(length=1)

      Results in this parsing structure::

           76543210  76543210
           fffff     bbbbbbbb

      Thus, ignoring bits 2-0 from the first byte.

StructField
===========
.. autoclass:: StructField

   The :class:`StructField` enables you to use Python :mod:`struct` constructs if you wish to. Note that using complex
   formats in this field kind-of defeats the purpose of this module.

   .. attribute:: StructField.format

      The format to be passed to the :mod:`struct` module. See
      `Struct Format Strings <https://docs.python.org/3/library/struct.html#format-strings>`_ in the manual of Python
      for information on how to construct these.

      You do not need to include the byte order in this attribute. If you do, it acts as a default for the
      :attr:`byte_order` attribute if you do not specify one.

   .. attribute:: StructField.byte_order

      The byte order to use for the struct. If this is not specified, and none is provided in the :attr:`format` field,
      it defaults to the ``byte_order`` specified in the meta of the :class:`destructify.structures.Structure`.

   .. attribute:: StructField.multibyte

      When set to :const:`False`, the Python representation of this field is the first result of the tuple as returned
      by the :mod:`struct` module. Otherwise, the tuple is the result.

Subclasses of StructField
-------------------------
This project also provides several default implementations for the different types of structs. For each of the
formats described in `Struct Format Strings <https://docs.python.org/3/library/struct.html#format-strings>`_, there
is a single-byte class. Note that you must specify your own

Each of the classes is listed in the table below.

.. hint::
   Use a :class:`IntegerField` when you know the amount of bytes you need to parse. Classes below are typically used
   for system structures and the :class:`IntegerField` is typically used for network structures.

+----------------------------------+--------+
| Base class                       | Format |
+==================================+========+
| :class:`CharField`               | ``c``  |
+----------------------------------+--------+
| :class:`ByteField`               | ``b``  |
+----------------------------------+--------+
| :class:`UnsignedByteField`       | ``B``  |
+----------------------------------+--------+
| :class:`BoolField`               | ``?``  |
+----------------------------------+--------+
| :class:`ShortField`              | ``h``  |
+----------------------------------+--------+
| :class:`UnsignedShortField`      | ``H``  |
+----------------------------------+--------+
| :class:`IntField`                | ``i``  |
+----------------------------------+--------+
| :class:`UnsignedIntField`        | ``I``  |
+----------------------------------+--------+
| :class:`LongField`               | ``l``  |
+----------------------------------+--------+
| :class:`UnsignedLongField`       | ``L``  |
+----------------------------------+--------+
| :class:`LongLongField`           | ``q``  |
+----------------------------------+--------+
| :class:`UnsignedLongLongField`   | ``Q``  |
+----------------------------------+--------+
| :class:`SizeField`               | ``n``  |
+----------------------------------+--------+
| :class:`UnsignedSizeField`       | ``N``  |
+----------------------------------+--------+
| :class:`HalfPrecisionFloatField` | ``e``  |
+----------------------------------+--------+
| :class:`FloatField`              | ``f``  |
+----------------------------------+--------+
| :class:`DoubleField`             | ``d``  |
+----------------------------------+--------+

StructureField
==============

.. autoclass:: StructureField

   The :class:`StructureField` is intended to create a structure that nests other structures. You can use this for
   complex structures, or when combined with for instance an :class:`ArrayField` to create arrays of structures, and
   when combined with :class:`SwitchField` to create type-based structures.

   .. attribute:: StructureField.structure

      The :class:`Structure` class that is initialized for the sub-structure.

   .. attribute:: StructureField.length

      The length of this structure. This allows you to limit the structure's length. This is particularly useful when
      you have a :class:`Structure` that contains an unbounded read.

   Example usage::

       >>> class Sub(Structure):
       ...     foo = FixedLengthField(length=11)
       ...
       >>> class Encapsulating(Structure):
       ...     bar = StructureField(Sub)
       ...
       >>> s = Encapsulating.from_bytes(b"hello world")
       >>> s
       <Encapsulating: Encapsulating(bar=<Sub: Sub(foo=b'hello world')>)>
       >>> s.bar
       <Sub: Sub(foo=b'hello world')>
       >>> s.bar.foo
       b'hello world'

ArrayField
==========

.. autoclass:: ArrayField

   A field that repeats the provided base field multiple times.

   .. attribute:: ArrayField.base_field

      The field that is to be repeated.

   .. attribute:: ArrayField.count

      This specifies the amount of repetitions of the base field.

      You can set it to one of the following:

      * A callable with zero arguments
      * A callable taking a :class:`ParsingContext` object
      * A string that represents the field name that contains the size
      * An integer

      The count given a context is obtained by calling ``ArrayField.get_count(value, context)``.

   .. attribute:: ArrayField.length

      This specifies the size of the field, if you do not know the count of the fields, but do know the size.

      You can set it to one of the following:

      * A callable with zero arguments
      * A callable taking a :class:`ParsingContext` object
      * A string that represents the field name that contains the size
      * An integer

      The length given a context is obtained by calling ``ArrayField.get_length(value, context)``.

      You can specify a negative length if you want to read until the stream ends. Note that this is currently
      implemented by swallowing a :class:`StreamExhaustedError` from the base field.

   Example usage::

       >>> class ArrayStructure(Structure):
       ...     count = UnsignedByteField()
       ...     foo = ArrayField(TerminatedField(terminator=b'\0'), count='count')
       ...
       >>> s = ArrayStructure.from_bytes(b"\x02hello\0world\0")
       >>> s.foo
       [b'hello', b'world']

ConditionalField
================
.. autoclass:: ConditionalField

   A field that may or may not be present. When the :attr:`condition` evaluates to true, the :attr:`base_field`
   field is parsed, otherwise the field is :const:`None`.

   .. attribute:: ConditionalField.base_field

      The field that is conditionally present.

   .. attribute:: ConditionalField.condition

      This specifies the condition on whether the field is present.

      You can set it to one of the following:

      * A callable with zero arguments
      * A callable taking a :class:`ParsingContext` object
      * A string that represents the field name that evaluates to true or false. Note that ``b'\0'`` evaluates to true.
      * A value that is to be evaluated

      The condition given a context is obtained by calling ``ConditionalField.get_condition(value, context)``.

SwitchField
===========
.. autoclass:: SwitchField

   The :class:`SwitchField` can be used to represent various types depending on some other value. You set the different
   cases using a dictionary of value-to-field-types in the :attr:`cases` attribute. The :attr:`switch` value defines
   the case that is applied. If none is found, an error is raised, unless :attr:`other` is set.

   .. attribute:: SwitchField.cases

      A dictionary of all cases mapping to a specific :class:`Field`.

   .. attribute:: SwitchField.switch

      This specifies the switch, i.e. the key for :attr:`cases`.

      You can set it to one of the following:

      * A callable with zero arguments
      * A callable taking a :class:`ParsingContext` object
      * A string that represents the field name that evaluates to the value of the condition
      * A value that is to be evaluated

   .. attribute:: SwitchField.other

      The 'default' case that is used when the :attr:`switch` is not part of the :attr:`cases`. If not specified, and
      an unknown value is encountered, an exception is raised.

      .. hint::

         A confusion is easily made by setting :attr:`Field.default` instead of :attr:`other`, though their purposes are
         entirely different.

   Example::

       class ConditionalStructure(Structure):
           type = EnumField(IntegerField(1), enum=Types)
           perms = SwitchField(cases={
               Types.FIRST: StructureField(Structure1),
               Types.SECOND: StructureField(Structure2),
           }, other=StructureField(Structure0), switch='type')

EnumField
=========
.. autoclass:: EnumField

   A field that takes the value as evaluated by the :attr:`base_field` and parses it as the provided :attr:`enum`.

   .. attribute:: EnumField.base_field

      The field that returns the value that is provided to the :class:`enum.Enum`

   .. attribute:: EnumField.enum

      The :class:`enum.Enum` class.

   You can also use an :class:`EnumField` to handle flags::

       >>> class Permissions(enum.IntFlag):
       ...     R = 4
       ...     W = 2
       ...     X = 1
       ...
       >>> class EnumStructure(Structure):
       ...     perms = EnumField(UnsignedByteField(), enum=Permissions)
       ...
       >>> EnumStructure.from_bytes(b"\x05")
       <EnumStructure: EnumStructure(perms=<Permissions.R|X: 5>)>