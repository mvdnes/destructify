import io
import unittest

from destructify import Structure, BitField, FixedLengthField, StructureField, MisalignedFieldError, \
    StringField, IntegerField, BytesField, VariableLengthIntegerField, ParsingContext, ParseError, \
    ImpossibleToCalculateLengthError, SwitchField
from destructify.exceptions import DefinitionError, StreamExhaustedError, WriteError
from tests import DestructifyTestCase


class PeekableBytesIO(io.BytesIO):
    def peek(self, size=-1):
        result = self.read(size)
        self.seek(-len(result), io.SEEK_CUR)
        return result


class BytesFieldTestCase(DestructifyTestCase):
    def test_initialize(self):
        with self.assertRaises(DefinitionError):
            BytesField(terminator=b'\0', padding=b'\0')
        with self.assertRaises(DefinitionError):
            BytesField()
        with self.assertRaises(DefinitionError):
            BytesField(terminator_handler='asdf', terminator=b'\0')
        with self.assertRaises(DefinitionError):
            BytesField(terminator_handler='until', length=3)

    def test_len(self):
        self.assertEqual(3, len(BytesField(length=3)))

        self.assertEqual(6, BytesField(length=3, skip=3)._length_sum(0))

    def test_length(self):
        self.assertFieldStreamEqual(b"abc", b"abc", BytesField(length=3))
        self.assertFieldStreamEqual(b"", b"", BytesField(length=0))
        self.assertFieldFromStreamEqual(b"abcdef", b"abc", BytesField(length=3))

    def test_dynamic_length(self):
        self.assertFieldStreamEqual(b"abc", b"abc", BytesField(length='length'),
                                    parsed_fields={'length': 3})
        self.assertFieldStreamEqual(b"abc", b"abc", BytesField(length=lambda c: 3))

    def test_dynamic_length_full(self):
        class Struct(Structure):
            len = IntegerField(length=1, byte_order='little')
            str1 = BytesField(length='len')

        self.assertStructureStreamEqual(b'\x05hello', Struct(len=5, str1=b'hello'))
        self.assertEqual(b'\x05hello', Struct(str1=b'hello').to_bytes())
        self.assertEqual(b'\x01h', Struct(len=1, str1=b'h').to_bytes())

    def test_dynamic_length_full_other_field_has_override(self):
        class Struct(Structure):
            len = IntegerField(length=1, byte_order='little', override=lambda c, v: v)
            str1 = BytesField(length='len')

        self.assertEqual(b'\x05hello', Struct(len=5, str1=b'hello').to_bytes())

        with self.assertRaises(Exception):
            Struct(str1=b'hello').to_bytes()

    def test_length_insufficient_bytes(self):
        with self.assertRaises(StreamExhaustedError):
            self.call_field_from_stream(BytesField(length=8), b"abc")
        self.call_field_from_stream(BytesField(length=8, strict=False), b"abc")

    def test_length_and_padding(self):
        self.assertFieldStreamEqual(b"a\0\0\0\0\0\0\0", b"a", BytesField(length=8, padding=b"\0"))
        self.assertFieldStreamEqual(b"aXPADXPAD", b"a", BytesField(length=9, padding=b"XPAD"))
        self.assertFieldStreamEqual(b"abcd\0\0", b"abcd", BytesField(length=6, padding=b"\0\0", step=2))
        self.assertFieldStreamEqual(b"abc\0\0\0", b"abc\0", BytesField(length=6, padding=b"\0\0", step=2))
        self.assertFieldStreamEqual(b"abc\0\0\0\0", b"abc", BytesField(length=7, padding=b"\0\0"))

    def test_length_and_misaligned_padding(self):
        with self.assertRaises(WriteError):
            self.call_field_to_stream(BytesField(length=7, padding=b"\0\0"), b"ab")
        self.assertFieldToStreamEqual(b"ab\0\0\0\0\0", b"ab", BytesField(length=7, padding=b"\0\0", strict=False))

    def test_length_write_insufficient_bytes(self):
        with self.assertRaises(WriteError):
            self.call_field_to_stream(BytesField(length=7), b"ab")
        self.assertFieldToStreamEqual(b"ab", b"ab", BytesField(length=7, strict=False))

    def test_length_write_too_many_bytes(self):
        with self.assertRaises(WriteError):
            self.call_field_to_stream(BytesField(length=2), b"abcdefg")
        self.assertFieldToStreamEqual(b"ab", b"abcdefg", BytesField(length=2, strict=False))

    def test_negative_length(self):
        self.assertFieldStreamEqual(b"abc", b"abc", BytesField(length=-1))
        self.assertFieldStreamEqual(b"", b"", BytesField(length=-1))
        self.assertFieldStreamEqual(b"asd\0", b"asd", BytesField(length=-1, terminator=b"\0"))

    def test_terminator(self):
        self.assertFieldStreamEqual(b"abcdef\0", b"abcdef", BytesField(terminator=b"\0"))
        self.assertFieldFromStreamEqual(b"abc\0def", b"abc", BytesField(terminator=b"\0"))

    def test_terminator_insufficient_bytes(self):
        with self.assertRaises(StreamExhaustedError):
            self.call_field_from_stream(BytesField(terminator=b'\0'), b"abc")
        self.assertFieldFromStreamEqual(b"abc", b"abc", BytesField(terminator=b'\0', strict=False))

    def test_multibyte_terminator(self):
        self.assertFieldStreamEqual(b"abcdef\0\0", b"abcdef", BytesField(terminator=b"\0\0"))
        self.assertFieldFromStreamEqual(b"a\0bc\0\0def", b"a\0bc", BytesField(terminator=b"\0\0"))
        self.assertFieldStreamEqual(b"abcde\0\0\0", b"abcde\0", BytesField(terminator=b"\0\0", step=2))

    def test_length_and_terminator(self):
        self.assertFieldStreamEqual(b"abcdef\0", b"abcdef", BytesField(length=7, terminator=b"\0"))
        self.assertFieldFromStreamEqual(b"abc\0def", b"abc", BytesField(length=7, terminator=b"\0"))

    def test_length_and_terminator_insufficient_bytes(self):
        with self.assertRaises(StreamExhaustedError):
            self.call_field_from_stream(BytesField(terminator=b'\0', length=3), b"abc")
        with self.assertRaises(StreamExhaustedError):
            self.call_field_from_stream(BytesField(terminator=b'\0\0', length=3), b"abc")
        with self.assertRaises(StreamExhaustedError):
            self.call_field_from_stream(BytesField(terminator=b'\0', length=8), b"abc")
        self.assertFieldFromStreamEqual(b"abc", b"abc", BytesField(length=3, terminator=b'\0', strict=False))
        self.assertFieldFromStreamEqual(b"ab", b"ab", BytesField(length=3, terminator=b'\0', strict=False))

    def test_length_and_multibyte_terminator(self):
        self.assertFieldStreamEqual(b"abcdef\0\0", b"abcdef", BytesField(terminator=b"\0\0", length=8))
        self.assertFieldFromStreamEqual(b"a\0bc\0\0def", b"a\0bc", BytesField(terminator=b"\0\0", length=9))
        self.assertFieldStreamEqual(b"abcde\0\0\0", b"abcde\0", BytesField(terminator=b"\0\0", step=2, length=8))

    def test_terminator_handler_consume(self):
        self.assertFieldStreamEqual(b"abcdef\0", b"abcdef", BytesField(terminator=b"\0", terminator_handler='consume'))

    def test_terminator_handler_include(self):
        self.assertFieldStreamEqual(b"abcdef\0", b"abcdef\0", BytesField(terminator=b"\0", terminator_handler='include'))
        with self.assertRaises(WriteError):
            self.call_field_to_stream(BytesField(terminator=b"\0", terminator_handler='include'), b"asdf")
        self.call_field_to_stream(BytesField(terminator=b"\0", terminator_handler='include', strict=False), b"asdf")

    def test_terminator_handler_until(self):
        self.assertFieldFromStreamEqual(b"abcdef\0gh", b"abcdef", BytesField(terminator=b"\0", terminator_handler='until'))
        self.assertFieldToStreamEqual(b"abcdef", b"abcdef", BytesField(terminator=b"\0", terminator_handler='until'))

    def test_terminator_handler_until_with_peek(self):
        pio = PeekableBytesIO(b"abcdef\0gh")
        field = BytesField(terminator=b"\0", terminator_handler='until')
        result = field.from_stream(pio, ParsingContext())
        self.assertEqual(b"abcdef", result[0])
        self.assertEqual(b"\0", pio.read(1))

    def test_terminator_handler_until_multibyte_misaligned_field(self):
        self.assertFieldFromStreamEqual(b"1231231\0\0", b"1231231",
                                        BytesField(terminator=b"\0\0", step=3, terminator_handler='until'))
        self.assertFieldFromStreamEqual(b"1231231\0\0", b"1231231",
                                        BytesField(terminator=b"\0\0", step=1, terminator_handler='until'))

    def test_terminator_handler_until_with_peek_multibyte_misaligned_field(self):
        with self.subTest("step larger than terminator length"):
            pio = PeekableBytesIO(b"1231231\0\0")
            field = BytesField(terminator=b"\0\0", step=3, terminator_handler='until')
            result = field.from_stream(pio, ParsingContext())
            self.assertEqual(b"1231231", result[0])
            self.assertEqual(b"\0\0", pio.read(2))

        with self.subTest("step smaller than terminator length"):
            pio = PeekableBytesIO(b"1231231\0\0")
            field = BytesField(terminator=b"\0\0", step=1, terminator_handler='until')
            result = field.from_stream(pio, ParsingContext())
            self.assertEqual(b"1231231", result[0])
            self.assertEqual(b"\0\0", pio.read(2))

    def test_terminator_handler_until_full(self):
        class Struct(Structure):
            str0 = BytesField(terminator=b'\0', terminator_handler='until')
            str1 = BytesField(length=3)

        self.assertStructureStreamEqual(b"asdf\0as", Struct(str0=b'asdf', str1=b'\0as'))

    def test_terminator_handler_consume_length(self):
        self.assertFieldStreamEqual(b"abcdef\0", b"abcdef",
                                    BytesField(terminator=b"\0", terminator_handler='consume', length=7))

    def test_terminator_handler_include_length(self):
        self.assertFieldToStreamEqual(b"abcdef\0", b"abcdef\0",
                                      BytesField(terminator=b"\0", terminator_handler='include', length=7))
        with self.assertRaises(WriteError):
            self.call_field_to_stream(BytesField(terminator=b"\0", terminator_handler='include', length=4), b"asdf")
        self.call_field_to_stream(BytesField(terminator=b"\0", terminator_handler='include', length=4, strict=False),
                                  b"asdf")


class BitFieldTest(unittest.TestCase):
    def test_parsing(self):
        class Struct(Structure):
            bit1 = BitField(length=3)
            bit2 = BitField(length=8)

        s = Struct.from_bytes(b"\xFF\xFF")
        self.assertEqual(0b111, s.bit1)
        self.assertEqual(0b11111111, s.bit2)

    def test_writing(self):
        class Struct(Structure):
            bit1 = BitField(length=3)
            bit2 = BitField(length=8)

        self.assertEqual(b"\xFF\xe0", Struct(bit1=0b111, bit2=0b11111111).to_bytes())

    def test_writing_full_bytes(self):
        class Struct(Structure):
            bit1 = BitField(length=3)
            bit2 = BitField(length=5)

        self.assertEqual(b"\xFF", Struct(bit1=0b111, bit2=0b111111).to_bytes())

        class Struct2(Structure):
            bit1 = BitField(length=3)
            bit2 = BitField(length=5)
            byte = FixedLengthField(length=1)

        self.assertEqual(b"\xFF\x33", Struct2(bit1=0b111, bit2=0b111111, byte=b'\x33').to_bytes())

    def test_misaligned_field(self):
        class Struct(Structure):
            bit1 = BitField(length=1)
            bit2 = BitField(length=1)
            byte = FixedLengthField(length=1)

        with self.assertRaises(ParseError) as cm:
            Struct.from_bytes(b"\xFF\xFF")
        self.assertIsInstance(cm.exception.__context__, MisalignedFieldError)

        with self.assertRaises(WriteError) as cm:
            self.assertEqual(b"\xc0\x33", Struct(bit1=1, bit2=1, byte=b'\x33').to_bytes())
        self.assertIsInstance(cm.exception.__context__, MisalignedFieldError)

    def test_misaligned_field_with_realign(self):
        class Struct(Structure):
            bit1 = BitField(length=1)
            bit2 = BitField(length=1, realign=True)
            byte = FixedLengthField(length=1)

        s = Struct.from_bytes(b"\xFF\xFF")
        self.assertEqual(1, s.bit1)
        self.assertEqual(1, s.bit2)
        self.assertEqual(b'\xFF', s.byte)

        self.assertEqual(b"\xc0\x33", Struct(bit1=1, bit2=1, byte=b'\x33').to_bytes())

    def test_field_with_structure_alignment(self):
        class Struct(Structure):
            bit1 = BitField(length=1)
            bit2 = BitField(length=1, realign=True)
            byte = FixedLengthField(length=1)

            class Meta:
                alignment = 2

        s = Struct.from_bytes(b"\xFF\0\xFF")
        self.assertEqual(1, s.bit1)
        self.assertEqual(1, s.bit2)
        self.assertEqual(b'\xFF', s.byte)

        self.assertEqual(b"\xc0\0\x33", Struct(bit1=1, bit2=1, byte=b'\x33').to_bytes())

    def test_field_with_structure_alignment_fails(self):
        class Struct(Structure):
            bit1 = BitField(length=1)
            byte = FixedLengthField(length=1)
            bit2 = BitField(length=1)

            class Meta:
                alignment = 2

        with self.assertRaises(ParseError) as cm:
            Struct.from_bytes(b"\xFF\0\xFF\0\xFF")
        self.assertIsInstance(cm.exception.__context__, MisalignedFieldError)

        with self.assertRaises(WriteError) as cm:
            Struct(bit1=1, bit2=1, byte=b'\x33').to_bytes()
        self.assertIsInstance(cm.exception.__context__, MisalignedFieldError)

    def test_field_structure_alignments(self):
        class Struct(Structure):
            bit1 = BitField(length=1, realign=True)
            byte = FixedLengthField(length=1)
            bit2 = BitField(length=1)

            class Meta:
                alignment = 2

        s = Struct.from_bytes(b"\xFF\0\xFF\0\xFF")
        self.assertEqual(1, s.bit1)
        self.assertEqual(1, s.bit2)
        self.assertEqual(b'\xFF', s.byte)

        self.assertEqual(b"\x80\0\x33\0\x80", Struct(bit1=1, bit2=1, byte=b'\x33').to_bytes())

    def test_length(self):
        class Struct(Structure):
            bit1 = BitField(length=3)
            bit2 = BitField(length=5)

        self.assertEqual(1, len(Struct))

    def test_length_realigned(self):
        class Struct(Structure):
            bit1 = BitField(length=3)
            bit2 = BitField(length=8, realign=True)

        self.assertEqual(2, len(Struct))

        class Struct(Structure):
            bit1 = BitField(length=3, realign=True)
            bit2 = BitField(length=8)

        self.assertEqual(2, len(Struct))

    def test_length_misaligned(self):
        class Struct(Structure):
            bit1 = BitField(length=3)
            bit2 = BitField(length=2)

        with self.assertRaises(ImpossibleToCalculateLengthError):
            len(Struct)

    def test_length_with_skip(self):
        class Struct(Structure):
            bit1 = BitField(length=8)
            bit2 = BitField(length=8, skip=2)

        self.assertEqual(4, len(Struct))


class StructureFieldTest(DestructifyTestCase):
    def test_parsing(self):
        class Struct1(Structure):
            byte1 = FixedLengthField(length=1)
            byte2 = FixedLengthField(length=1)

        class Struct2(Structure):
            s1 = StructureField(Struct1)
            s2 = StructureField(Struct1)

        self.assertStructureStreamEqual(b"\x01\x02\03\x04", Struct2(s1=Struct1(byte1=b"\x01", byte2=b"\x02"),
                                                                    s2=Struct1(byte1=b"\x03", byte2=b"\x04")))

    def test_referencing_parent(self):
        class Struct1(Structure):
            b = FixedLengthField(length=lambda c: c._.length, )

        class Struct2(Structure):
            length = IntegerField(length=1, override=lambda c, v: len(c.s2.b))
            s2 = StructureField(Struct1)

        # explicitly testing override and length, so not using assertStructureStreamEqual
        self.assertEqual(Struct2(length=1, s2=Struct1(b=b"\x02")), Struct2.from_bytes(b"\x01\x02"))
        self.assertEqual(b"\x01\x02", bytes(Struct2(s2=Struct1(b=b"\x02"))))

    def test_unlimited_substructure(self):
        class UnlimitedFixedLengthStructure(Structure):
            text = FixedLengthField(length=-1)

        class UFLSStructure(Structure):
            s = StructureField(UnlimitedFixedLengthStructure, length=5)

        # "Test UnlimitedFixedLengthStructure is unlimited"
        ufls = UnlimitedFixedLengthStructure.from_bytes(b"\x01\x02\x03\x04\x05\x06")
        self.assertEqual(b"\x01\x02\x03\x04\x05\x06", ufls.text)

        # "Test reading from UFLSStructure is not unlimited"
        ufls = UFLSStructure.from_bytes(b"\x01\x02\x03\x04\x05\x06")
        self.assertEqual(b"\x01\x02\x03\x04\x05", ufls.s.text)

        # Test reading/writing the stream
        self.assertStructureStreamEqual(b"\x01\x02\x03\x04\x05",
                                        UFLSStructure(s=UnlimitedFixedLengthStructure(text=b"\x01\x02\x03\x04\x05")))

        # Test writing too much is not OK
        with self.assertRaises(WriteError):
            UFLSStructure(s=UnlimitedFixedLengthStructure(text=b"\x01\x02\x03\x04\x05\x06")).to_bytes()

    def test_structure_that_skips_bytes(self):
        class ShortStructure(Structure):
            text = FixedLengthField(length=3)

        class StructureThatSkips(Structure):
            s = StructureField(ShortStructure, length=5)
            text = FixedLengthField(length=3)

        self.assertStructureStreamEqual(b"\x01\x02\x03\x00\x00\x06\x07\x08",
                                        StructureThatSkips(s=ShortStructure(text=b"\x01\x02\x03"), text=b"\x06\x07\x08"))

    def test_fieldcontext(self):
        class Struct1(Structure):
            byte1 = FixedLengthField(length=1)

        class Struct2(Structure):
            s = StructureField(Struct1)

        with self.subTest("from_stream"):
            context = ParsingContext()
            Struct2.from_stream(io.BytesIO(b"\0"), context)

            self.assertIsInstance(context.fields['s'].subcontext, ParsingContext)
            self.assertEqual(b"\0", context.fields['s'].subcontext.fields['byte1'].value)

        with self.subTest("to_stream"):
            context = ParsingContext()
            Struct2(s=Struct1(byte1=b"\0")).to_stream(io.BytesIO(), context)

            self.assertIsInstance(context.fields['s'].subcontext, ParsingContext)
            self.assertEqual(b"\0", context.fields['s'].subcontext.fields['byte1'].value)


class StringFieldTest(DestructifyTestCase):
    def test_fixed_length(self):
        self.assertFieldStreamEqual(b"abcde", 'abcde', StringField(length=5, encoding='utf-8'))
        self.assertFieldStreamEqual(b'\xfc\0b\0e\0r\0', '\xfcber', StringField(length=8, encoding='utf-16-le'))
        self.assertFieldStreamEqual(b'b\0y\0e\0b\0y\0e\0', 'byebye', StringField(length=12, encoding='utf-16-le'))

    def test_fixed_length_error(self):
        with self.assertRaises(UnicodeDecodeError):
            self.call_field_from_stream(StringField(length=7, encoding='utf-16-le'), b'\xfc\0b\0e\0r')

        self.assertFieldFromStreamEqual(b'\xfc\0b\0e\0r', "\xfcbe\uFFFD",
                                        StringField(length=7, encoding='utf-16-le', errors='replace'))
        self.assertFieldFromStreamEqual(b'h\0\0\0\0\0', "h\0\0",
                                        StringField(length=6, encoding='utf-16-le'))

    def test_terminated(self):
        self.assertFieldStreamEqual(b"abcde\0", 'abcde', StringField(terminator=b'\0', encoding='utf-8'))
        self.assertFieldStreamEqual(b'b\0y\0e\0\0\0', 'bye', StringField(terminator=b'\0\0', step=2, encoding='utf-16-le'))

    def test_encoding_from_meta(self):
        with self.assertRaises(DefinitionError):
            class Struct(Structure):
                str = StringField(length=2)
                class Meta:
                    encoding = None

        class Struct2(Structure):
            str = StringField(length=2)
            class Meta:
                encoding = 'utf-8'

        self.assertEqual("ba", Struct2.from_bytes(b"ba").str)

        class Struct3(Structure):
            str = StringField(length=2)
            class Meta:
                encoding = 'utf-16-le'

        self.assertEqual("b", Struct3.from_bytes(b"b\0").str)

        class Struct4(Structure):
            str = StringField(length=2, encoding='utf-8')
            class Meta:
                encoding = 'utf-16-le'

        self.assertEqual("ba", Struct4.from_bytes(b"ba").str)


class IntegerFieldTest(DestructifyTestCase):
    def test_basic(self):
        self.assertFieldStreamEqual(b'\x01\0', 256, IntegerField(2, 'big'))
        self.assertFieldStreamEqual(b'\x01\0', 1, IntegerField(2, 'little'))
        self.assertFieldStreamEqual(b'\xff\xfe', -257, IntegerField(2, 'little', signed=True))
        self.assertFieldStreamEqual(b'\xff\xfe', 65534, IntegerField(2, 'big', signed=False))
        self.assertFieldStreamEqual(b'\xfe\xff', -257, IntegerField(2, 'big', signed=True))

    def test_writing_overflow(self):
        with self.assertRaises(OverflowError):
            self.assertFieldToStreamEqual(None, 1000, IntegerField(1, 'little'))
        with self.assertRaises(OverflowError):
            self.assertFieldToStreamEqual(None, -1000, IntegerField(1, 'little'))

    def test_parsing_with_byte_order_on_structure(self):
        with self.assertRaises(DefinitionError):
            class Struct(Structure):
                num = IntegerField(2)

        class Struct2(Structure):
            num = IntegerField(2)
            class Meta:
                byte_order = 'little'

        self.assertEqual(513, Struct2.from_bytes(b"\x01\x02").num)

        class Struct3(Structure):
            num = IntegerField(2)
            class Meta:
                byte_order = 'big'

        self.assertEqual(258, Struct3.from_bytes(b"\x01\x02").num)

    def test_parsing_and_writing_without_byte_order_single_byte(self):
        class Struct(Structure):
            num = IntegerField(1)

        self.assertEqual(1, Struct.from_bytes(b"\x01").num)
        self.assertEqual(b'\x01', Struct(num=1).to_bytes())


class VariableLengthQuantityFieldTest(DestructifyTestCase):
    def test_basic(self):
        self.assertFieldStreamEqual(b'\x00', 0x00, VariableLengthIntegerField())
        self.assertFieldStreamEqual(b'\x7f', 0x7f, VariableLengthIntegerField())
        self.assertFieldStreamEqual(b'\x81\x00', 0x80, VariableLengthIntegerField())
        self.assertFieldStreamEqual(b'\xc0\x00', 0x2000, VariableLengthIntegerField())
        self.assertFieldStreamEqual(b'\xff\x7f', 16383, VariableLengthIntegerField())
        self.assertFieldStreamEqual(b'\x81\x80\x00', 16384, VariableLengthIntegerField())
        self.assertFieldStreamEqual(b'\x81\x80\x80\x00', 2097152, VariableLengthIntegerField())
        self.assertFieldStreamEqual(b'\xff\xff\xff\x7f', 268435455, VariableLengthIntegerField())
        self.assertFieldFromStreamEqual(b'\xff\xff\xff\x7f\x00\x00', 268435455, VariableLengthIntegerField())
        self.assertFieldFromStreamEqual(b'\x80\x80\x7f', 0x7f, VariableLengthIntegerField())

    def test_negative_value(self):
        with self.assertRaises(OverflowError):
            self.call_field_to_stream(VariableLengthIntegerField(), -1)

    def test_stream_not_sufficient(self):
        with self.assertRaises(StreamExhaustedError):
            self.call_field_from_stream(VariableLengthIntegerField(), b'\x81\x80\x80')


class SwitchFieldTest(DestructifyTestCase):
    def test_basic_switch(self):
        self.assertFieldStreamEqual(b"\x01", 1,
                                    SwitchField(cases={1: IntegerField(1), 2: IntegerField(2, 'little')}, switch=1))
        self.assertFieldStreamEqual(b"\x01\x01", 0x0101,
                                    SwitchField(cases={1: IntegerField(1), 2: IntegerField(2, 'little')}, switch=2))
        self.assertFieldStreamEqual(b"\x01", 1,
                                    SwitchField(cases={1: IntegerField(1), 2: IntegerField(2, 'little')}, switch='c'),
                                    parsed_fields={'c': 1})

    def test_switch_other(self):
        self.assertFieldStreamEqual(b"\x01", 1, SwitchField(cases={}, other=IntegerField(1), switch=1))

    def test_nested_bitfield(self):
        # explicit test due to it requiring a stream wrapper
        class TestStructure(Structure):
            value = SwitchField(cases={1: BitField(1), 2: BitField(1)}, switch=2)

        ts = TestStructure.from_bytes(b"\xff")
        self.assertEqual(1, ts.value)
