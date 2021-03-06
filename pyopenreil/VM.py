import sys, os, struct, random
import numpy

from REIL import *

class MemError(Error):

    def __init__(self, addr):

        self.addr = addr

    def __str__(self):

        return 'Error while acessing memory at address %s' % hex(self.addr)


class MemReadError(MemError):

    def __str__(self):

        return 'Error while reading memory at address %s' % hex(self.addr)


class MemWriteError(MemError):

    def __str__(self):

        return 'Error while writing memory at address %s' % hex(self.addr)


class CpuError(Error):

    def __init__(self, addr, inum = 0):

        self.addr, self.inum, = addr, inum


class CpuReadError(CpuError):

    def __str__(self):

        return 'Error while reading instruction %s' % hex(self.addr)


class CpuInstructionError(CpuError):

    def __str__(self):

        return 'Invalid instruction at %s.%.2d' % (hex(self.addr), self.inum)


class Mem(object):

    # start address for memory allocations
    DEF_ALLOC_BASE = 0x11000000

    # REIL type to length map
    map_length = { U8: 1, U16: 2, U32: 4, U64: 8 }

    # length to REIL type map
    map_size = { 1: U8, 2: U16, 4: U32, 8: U64 }

    # REIL type to struct format map
    map_format = { U8: 'B', U16: 'H', U32: 'I', U64: 'Q' }    

    def __init__(self, data = None, reader = None, strict = True):

        self.data = {} if data is None else None
        self.reader, self.strict = reader, strict
        self.alloc_base = self.DEF_ALLOC_BASE
        self.alloc_last = self.alloc_base

    def pack(self, size, val):

        return struct.pack(self.map_format[size], val)

    def unpack(self, size, val):

        return struct.unpack(self.map_format[size], val)[0] 

    def clear(self):

        self.data = {}

    def _read(self, addr, size):

        data = ''

        for i in range(0, size):

            if not self.data.has_key(addr + i):

                raise MemReadError(addr)

            data += self.data[addr + i]

        return data

    def _write(self, addr, size, data):

        for i in range(0, size):

            if not self.data.has_key(addr + i):

                raise MemWriteError(addr)

            self.data[addr + i] = data[i]

    def read(self, addr, size):

        try:

            return self._read(addr, size)

        except MemReadError:

            if self.reader is None: raise

            # invalid address, try to get the data from external memory reader
            data = self.reader.read(addr, size)
            if data is None: 

                raise

            # copy data from external storage
            self.alloc(addr, data = data)
            return data

    def write(self, addr, size, data):

        try:

            self._write(addr, size, data)

        except MemWriteError:

            if self.strict:

                if self.reader is None: raise

                # invalid address, check if memory reader knows it
                if self.reader.read(addr, size) is None: 

                    raise

            # allocate memory at adderss that was not available
            self.alloc(addr, data = data)

    def alloc_addr(self, size):

        ret = self.alloc_last
        self.alloc_last += size

        return ret

    def alloc(self, addr = None, size = None, data = None):

        size = len(data) if size is None and not data is None else size
        addr = self.alloc_addr(size) if addr is None else addr

        for i in range(0, size):

            # fill target memory range with specified data (or zeros)
            byte = '\0' if data is None or i >= len(data) else data[i]
            self.data[addr + i] = byte

        return addr

    def store(self, addr, size, val):

        self.write(addr, self.map_length[size], self.pack(size, val))

    def load(self, addr, size):

        val = self.read(addr, self.map_length[size])

        return self.unpack(size, val)

    def dump_hex(self, data, width = 16, addr = None):

        def quoted(data):

            # replace non-alphanumeric characters
            return ''.join(map(lambda b: b if b.isalnum() else '.', data))

        while data:

            line = data[: width]
            data = data[width :]

            s = map(lambda b: '%.2x' % ord(b), line)
            s += [ '  ' ] * (width - len(line))

            s = '%s | %s' % (' '.join(s), quoted(line))
            if addr is not None: s = '%.8x: %s' % (addr, s)

            print s

            addr += len(line)

    def dump(self, addr, size):

        # read and dump memory contents
        self.dump_hex(self.read(addr, size), addr = addr)


class TestMem(unittest.TestCase):

    def test(self):     

        mem = Mem(strict = False)
        val = 0x1111111122224488

        mem.store(0, U64, 0x1111111111111111)
        mem.store(0, U32, 0x22222222)
        mem.store(0, U16, 0x4444)
        mem.store(0, U8, 0x88)
        
        assert mem.data == { 0: chr(0x88), 1: chr(0x44), 2: chr(0x22), 3: chr(0x22),
                             4: chr(0x11), 5: chr(0x11), 6: chr(0x11), 7: chr(0x11) }
        
        assert mem.load(0, U64) == val and \
               mem.load(0, U32) == val & 0xffffffff and \
               mem.load(0, U16) == val & 0xffff and \
               mem.load(0, U8) == val & 0xff


class Math(object):

    def __init__(self, a = None, b = None):

        self.a, self.b = a, b    

    def val(self, arg):

        return None if arg is None else arg.get_val()

    def val_u(self, arg):

        # Arg to numpy unsigned integer
        return None if arg is None else {
            
             U1: numpy.uint8, 
             U8: numpy.uint8, 
            U16: numpy.uint16,
            U32: numpy.uint32, 
            U64: numpy.uint64  

        }[arg.size](self.val(arg))

    def val_s(self, arg):

        # Arg to numpy signed integer
        return None if arg is None else { 

             U1: numpy.int8, 
             U8: numpy.int8, 
            U16: numpy.int16,
            U32: numpy.int32, 
            U64: numpy.int64  

        }[arg.size](self.val_u(arg))

    def eval(self, op, a = None, b = None):

        a = self.a if a is None else a
        b = self.b if b is None else b

        # evaluale unsigned/unsigned expressions
        eval_u = lambda fn: fn(self.val_u(a), self.val_u(b)).item()
        eval_s = lambda fn: fn(self.val_s(a), self.val_s(b)).item()        

        return { 

            I_STR: lambda: a.get_val(),            
            I_ADD: lambda: eval_u(lambda a, b: a +  b ),
            I_SUB: lambda: eval_u(lambda a, b: a -  b ),            
            I_NEG: lambda: eval_u(lambda a, b:     -a ),
            I_MUL: lambda: eval_u(lambda a, b: a *  b ),
            I_DIV: lambda: eval_u(lambda a, b: a /  b ),
            I_MOD: lambda: eval_u(lambda a, b: a %  b ),
           I_SMUL: lambda: eval_s(lambda a, b: a *  b ),
           I_SDIV: lambda: eval_s(lambda a, b: a /  b ),
           I_SMOD: lambda: eval_s(lambda a, b: a %  b ),
            I_SHL: lambda: eval_u(lambda a, b: a << b ),
            I_SHR: lambda: eval_u(lambda a, b: a >> b ),
            I_AND: lambda: eval_u(lambda a, b: a &  b ),
             I_OR: lambda: eval_u(lambda a, b: a |  b ),
            I_XOR: lambda: eval_u(lambda a, b: a ^  b ),            
            I_NOT: lambda: eval_u(lambda a, b:     ~a ),
             I_EQ: lambda: eval_u(lambda a, b: a == b ),
             I_LT: lambda: eval_u(lambda a, b: a <  b ) 

        }[op]()


class TestMath(unittest.TestCase):

    def test(self):     

        pass


class Reg(object):

    def __init__(self, name, val, is_temp = False):

        self.name, self.val, self.is_temp = name, val, is_temp


class Cpu(object):

    DEF_REG_VAL = 0L

    def __init__(self, arch, mem = None, math = None):

        self.mem = Mem() if mem is None else mem
        self.math = Math() if math is None else math
        self.arch = get_arch(arch)
        self.reset()

    def set_storage(self, storage = None):

        self.mem.reader = None if storage is None else storage.reader

    def reset(self, regs = None, mem = None):

        if regs is not None:

            # set up caller specified registers set
            for name, val in regs.items(): self.reg(name, val = val)

        else: self.regs = {}

        if mem is not None:

            self.mem = mem

    def reset_temp(self):

        for name, reg in self.regs.items():

            if reg.is_temp: self.regs.pop(name)

    def reg(self, name, val = DEF_REG_VAL, is_temp = False):

        name = name.upper()
        if not name[:2] in [ 'R_', 'V_' ]:

            # make canonical register name
            name = '%s_%s' % ( 'V' if is_temp else 'R', name )

        if not self.regs.has_key(name): 

            reg = self.regs[name] = Reg(name, val, is_temp = is_temp)

        else: 

            reg = self.regs[name]

        return reg

    def arg(self, arg):

        if arg.type == A_REG: 

            return Arg(A_CONST, arg.size, val = self.reg(arg.name).val)
        
        if arg.type == A_TEMP: 

            return Arg(A_CONST, arg.size, val = self.reg(arg.name, is_temp = True).val)

        if arg.type == A_CONST: 

            return arg

        if arg.type == A_NONE: 

            return None

    def evaluate(self, op, size, a, b):

        return Arg(A_CONST, size, val = self.math.eval(op, a, b))

    def insn_none(self, insn, a, b, c):

        return None

    def insn_jcc(self, insn, a, b, c):

        # return address of the next instruction to execute if condition was taken
        return c.get_val() if a.get_val() != 0 else None

    def insn_stm(self, insn, a, b, c):

        # store a to memory
        self.mem.store(c.get_val(), insn.a.size, a.get_val())
        return None

    def insn_ldm(self, insn, a, b, c):

        # read from memory to c
        self.reg(insn.c.name).val = self.mem.load(a.get_val(), insn.c.size)
        return None

    def insn_other(self, insn, a, b, c):

        # evaluate all other instructions
        self.reg(insn.c.name).val = self.evaluate(insn.op, insn.c.size, a, b).get_val()        
        return None

    def execute(self, insn):

        # get arguments values
        a, b, c = self.arg(insn.a), self.arg(insn.b), self.arg(insn.c)
        
        if not insn.op in REIL_INSN:

            # invalid opcode
            raise CpuInstructionError(insn.addr, insn.inum)

        try:
            
            return {

                I_NONE: self.insn_none,
                 I_JCC: self.insn_jcc,
                 I_STM: self.insn_stm,
                 I_LDM: self.insn_ldm

            # call opcode-specific handler
            }[insn.op](insn, a, b, c)

        except KeyError:

            return self.insn_other(insn, a, b, c)

    def get_ip(self):

        return self.reg(self.arch.Registers.ip).get_val()

    def set_ip(self, val):

        self.reg(self.arch.Registers.ip).val = val

    def run(self, storage, addr = 0L):

        next = addr

        # use specified storage instance
        self.set_storage(storage)        
        self.set_ip(next)

        while True:
            
            try:

                # query list of IR instructions from storage                
                insn_list = storage.get_insn(next)

            except StorageError:

                raise CpuReadError(next)

            for insn in insn_list:

                # execute single instruction
                next = self.execute(insn)

                # check if JCC was taken
                if next is not None: break
                else: next, _ = insn.next()

                self.set_ip(next)

            # remove temp registers
            self.reset_temp()

        self.set_storage()

    def dump(self, show_flags = True, show_temp = False):

        # dump main registers
        for name, reg in self.regs.items():

            if name in self.arch.Registers.general:

                print '%8s: %.16x' % (name, reg.val)

        if show_flags:

            # dump flags
            for name, reg in self.regs.items():

                if name in self.arch.Registers.flags:

                    print '%8s: %.16x' % (name, reg.val)

        if show_temp:

            # dump temp registers
            for reg in self.regs.values():

                if reg.is_temp:

                    print '%8s: %.16x' % (reg.name, reg.val)

    def dump_mem(self, addr, size): 

        self.mem.dump(addr, size)


class TestCpu(unittest.TestCase):

    arch = ARCH_X86

    def test(self):     

        code = ( 'mov eax, edx',
                 'add eax, ecx', 
                 'ret' )

        addr, stack = 0x41414141, 0x42424242

        # create reader and translator
        from pyopenreil.utils import asm
        tr = CodeStorageTranslator(asm.Reader(self.arch, code, addr = addr))
        
        cpu = Cpu(self.arch)

        # set up stack pointer and input args
        cpu.reg('esp').val = stack
        cpu.reg('ecx').val = 1
        cpu.reg('edx').val = 2

        # run untill ret
        try: cpu.run(tr, addr)
        except MemReadError as e: 

            # exception on accessing to the stack
            if e.addr != stack: raise

        # check for correct return value
        assert cpu.reg('eax').val == 3

    def test_code_read(self):

        addr, stack = 0x41414141, 0x42424242
    
        # test code that reads itself
        code = ( 'nop', 'nop', 
                 'nop', 'nop', 
                 'mov eax, dword [%Xh]' % addr, 
                 'ret' )

        # create reader and translator
        from pyopenreil.utils import asm
        tr = CodeStorageTranslator(asm.Reader(self.arch, code, addr = addr))

        cpu = Cpu(ARCH_X86)

        # set up stack pointer
        cpu.reg('esp').val = stack
        
        # run untill ret
        try: cpu.run(tr, addr)
        except MemReadError as e: 

            # exception on accessing to the stack
            if e.addr != stack: raise

        # check for correct return value
        assert cpu.reg('eax').val == 0x90909090


class Stack(object):

    # start address of stack memory
    DEF_STACK_BASE = 0x12000000

    def __init__(self, mem, item_size, addr = None, size = None):

        self.size = 0x1000 if size is None else size
        self.addr = mem.alloc(addr = self.DEF_STACK_BASE, size = self.size)

        self.top = self.bottom = self.addr + self.size
        self.mem, self.item_size = mem, item_size

    def push(self, val):

        self.top -= self.item_size
        self.mem.store(self.top, Mem.map_size[self.item_size], val)

    def pop(self):

        val = self.mem.load(self.top, Mem.map_size[self.item_size])
        self.top += self.item_size

        return val


class TestStack(unittest.TestCase):

    arch = ARCH_X86

    def test(self):     

        code = ( 'pop ecx', 
                 'pop eax', 
                 'jmp ecx'  )

        addr, arg, ret = 0x41414141, 0x42424242, 0x43434343        

        # create reader and translator        
        from pyopenreil.utils import asm
        tr = CodeStorageTranslator(asm.Reader(self.arch, code, addr = addr))

        cpu = Cpu(self.arch)

        from pyopenreil.arch import x86
        stack = Stack(cpu.mem, x86.ptr_len)

        # set up stack arg and return address
        stack.push(arg)
        stack.push(ret)
        cpu.reg(x86.Registers.sp, stack.top)

        try:

            # run untill ret
            cpu.run(tr, addr)

        except CpuReadError as e: 

            # exception on accessing to the stack
            if e.addr != ret: raise

        # check for correct return value
        cpu.reg('eax').val == arg


class Abi(object):

    DUMMY_RET_ADDR = 0xcafebabe;

    def __init__(self, cpu, storage):

        self.cpu = cpu
        self.mem, self.arch = cpu.mem, cpu.arch
        self.storage = storage

        self.reset()

    def align(self, val):

        return val + (self.arch.ptr_len - val % self.arch.ptr_len)

    def read(self, addr, size):

        return self.mem.read(addr, size)

    def buff(self, data, addr = None, fill = None):

        if isinstance(data, basestring):

            # data was passed 
            size = len(data)

        else:

            # length was passed
            size = data
            data = None if fill is None else fill * size

        return self.mem.alloc(addr = addr, size = self.align(size), data = data)

    def string(self, data):

        # allocate null terminated buffer
        return self.buff(data + '\0\0\0\0')

    def stack(self, size = None):

        return Stack(self.mem, self.arch.ptr_len, size = size)

    def pushargs(self, args):

        args = list(args)
        args.reverse()

        # push arguments into the stack
        stack = self.stack()        
        for a in args: 

            # copy buffers into the memory
            a = self.string(a) if isinstance(a, basestring) else a
            stack.push(a)

        return stack

    def initial_regs(self):

        regs = {}
        regs.update(map(lambda name: (name, 0L), self.arch.Registers.general + \
                                                 self.arch.Registers.flags))
        return regs

    def reset(self):

        # clear memory
        self.mem.clear()

        # reset cpu state
        self.cpu.reset(self.initial_regs())

    def reg(self, name, val = None):

        # get/set register value
        if val is None: return self.cpu.reg(name).val
        else: self.cpu.reg(name).val = val

    def call(self, addr, *args):

        # prepare stack for call
        stack = self.pushargs(args)            
        stack.push(self.DUMMY_RET_ADDR)

        self.reg(self.arch.Registers.sp, stack.top)

        try:

            # run untill cpu will stop on DUMMY_RET_ADDR
            self.cpu.run(self.storage, addr)

        except CpuError as e:

            if e.addr != self.DUMMY_RET_ADDR:

                raise
    
    def stdcall(self, addr, *args):        

        # init cpu and call target function
        self.reg(self.arch.Registers.accum, 0)        
        self.call(addr, *args)

        # return accumulator value
        return self.reg(self.arch.Registers.accum)

    def cdecl(self, addr, *args):

        # we never need to care about stack cleanup
        return self.stdcall(addr, *args)

    def ms_fastcall(self, addr, *args):

        if len(args) > 0:

            first = args[0]
            args = args[1:]

            self.reg('ecx', first)

        if len(args) > 0:

            second = args[0]
            args = args[1:]

            self.reg('edx', second)

        return self.stdcall(addr, *args)


class TestAbi(unittest.TestCase):

    arch = ARCH_X86

    def test(self):     

        code = ( 'pop ecx', 
                 'pop eax', 
                 'jmp ecx'  )   

        addr, arg = 0x41414141, 0x42424242

        # create reader and translator        
        from pyopenreil.utils import asm
        tr = CodeStorageTranslator(asm.Reader(self.arch, code, addr = addr))

        cpu = Cpu(self.arch)
        abi = Abi(cpu, tr)

        # check for correct return value
        assert abi.stdcall(addr, arg) == arg

#
# EoF
#
