# uWSGI build system

uwsgi_version = '1.3-dev'

import os
import re
import time
uwsgi_os = os.uname()[0]
uwsgi_os_k = re.split('[-+]', os.uname()[2])[0]
uwsgi_os_v = os.uname()[3]
uwsgi_cpu = os.uname()[4]

import sys
import subprocess

from distutils import sysconfig

try:
    import ConfigParser
except:
    import configparser as ConfigParser
    from imp import reload

GCC = os.environ.get('CC', sysconfig.get_config_var('CC'))
if not GCC:
    GCC = 'gcc'

CPP = os.environ.get('CPP', 'cpp')

binary_list = []
	
def binarize(name):
    return name.replace('/', '_').replace('.','_').replace('-','_')

def spcall(cmd):
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE,stderr=open('uwsgibuild.log','w'))

    if p.wait() == 0:
        if sys.version_info[0] > 2:
            return p.stdout.read().rstrip().decode()
        return p.stdout.read().rstrip()
    else:
        return None

# commodity function to remove -W* duplicates
def uniq_warnings(elements):
    new_elements = []
    for element in elements:
        if element.startswith('-W'):
            if not element in new_elements:
                new_elements.append(element)
        else:
            new_elements.append(element)

    return new_elements

if uwsgi_version.endswith('-dev') and os.path.exists('%s/.hg' % os.path.dirname(os.path.abspath( __file__ ))):
    try:
        uwsgi_version += spcall('hg tip --template "-{rev}"')
    except:
        pass


def spcall2(cmd):
    p = subprocess.Popen(cmd, shell=True, stderr=subprocess.PIPE)

    if p.wait() == 0:
        if sys.version_info[0] > 2:
            return p.stderr.read().rstrip().decode()
        return p.stderr.read().rstrip()
    else:
        return None

def spcall3(cmd):
    p = subprocess.Popen(cmd, shell=True, stdin=open('/dev/null'), stderr=subprocess.PIPE, stdout=subprocess.PIPE)

    if p.wait() == 0:
        if sys.version_info[0] > 2:
            return p.stderr.read().rstrip().decode()
        return p.stderr.read().rstrip()
    else:
        return None


def add_o(x):
    if x == 'uwsgi':
        x = 'main'
    elif x.endswith('.a'):
        return x
    x = x + '.o'
    return x


def compile(cflags, objfile, srcfile):
    source_stat = os.stat(srcfile)
    header_stat = os.stat('uwsgi.h')
    try:
        if os.environ.get('UWSGI_FORCE_REBUILD', None):
            raise
        object_stat = os.stat(objfile)
        if object_stat[8] <= source_stat[8]:
            raise
        if object_stat[8] <= header_stat[8]:
            raise
        for profile in os.listdir('buildconf'):
            profile_stat = os.stat('buildconf/%s' % profile)
            if object_stat[8] <= profile_stat[8]:
                raise
        print("%s is up to date" % objfile)
        return
    except:
        pass
    cmdline = "%s -c %s -o %s %s" % (GCC, cflags, objfile, srcfile)
    print("[%s] %s" % (GCC, objfile))
    ret = os.system(cmdline)
    if ret != 0:
        sys.exit(1)


def build_uwsgi(uc, print_only=False):

    gcc_list, cflags, ldflags, libs = uc.get_gcll()

    if uc.get('embedded_plugins'):
        ep = uc.get('embedded_plugins').split(',')
        epc = "-DUWSGI_DECLARE_EMBEDDED_PLUGINS=\""
        eplc = "-DUWSGI_LOAD_EMBEDDED_PLUGINS=\""
        for p in ep:
            if p is None or p == 'None':
                continue
            p = p.strip()
            if p == 'ugreen':
                if uwsgi_os == 'OpenBSD' or uwsgi_cpu[0:3] == 'arm' or uwsgi_os == 'Haiku':
                    continue
            epc += "UDEP(%s);" % p
            eplc += "ULEP(%s);" % p
        epc += "\""
        eplc += "\""

        cflags.append(epc)
        cflags.append(eplc)

    if print_only:
        print(' '.join(cflags))
        sys.exit(0)

    print("configured CFLAGS: %s" % ' '.join(cflags))

    print("*** uWSGI compiling server core ***")
    for file in gcc_list:
        objfile = file
        if objfile == 'uwsgi':
            objfile = 'main'
        if not objfile.endswith('.a'):
            compile(' '.join(cflags), objfile + '.o', file + '.c')

    if uc.get('embedded_plugins'):
        ep = uc.get('embedded_plugins').split(',')

        if len(ep) > 0:
            print("*** uWSGI compiling embedded plugins ***")
            for p in ep:
                if p is None or p == 'None':
                    continue
                p = p.strip()

                if p == 'ugreen':
                    if uwsgi_os == 'OpenBSD' or uwsgi_cpu[0:3] == 'arm' or uwsgi_os == 'Haiku':
                        continue
                path = 'plugins/%s' % p
                path = path.rstrip('/')

                sys.path.insert(0, path)
                import uwsgiplugin as up
                reload(up)

                p_cflags = cflags[:]
                p_cflags += up.CFLAGS

                try:
                    p_cflags.remove('-Wdeclaration-after-statement')
                except:
                    pass

                try:
                    p_cflags.remove('-Werror=declaration-after-statement')
                except:
                    pass

                try:
                    p_cflags.remove('-Wwrite-strings')
                except:
                    pass

                try:
                    p_cflags.remove('-Werror=write-strings')
                except:
                    pass

                for cfile in up.GCC_LIST:
                    if not cfile.endswith('.a'):
                        compile(' '.join(uniq_warnings(p_cflags)),
                            path + '/' + cfile + '.o', path + '/' + cfile + '.c')
                        gcc_list.append('%s/%s' % (path, cfile))
                    else:
                        gcc_list.append(cfile)

                libs += up.LIBS
                ldflags += up.LDFLAGS

                up.CFLAGS = None
                up.LDFLAGS = None
                up.LIBS = None
                up.GCC_LIST = None

    if uc.get('plugins'):

        plugins = uc.get('plugins').split(',')
        if len(plugins) > 0:
            print("*** uWSGI building plugins ***")

            for p in plugins:
                p = p.strip()
                print("*** building plugin: %s ***" % p)
                build_plugin("plugins/%s" % p, uc, cflags, ldflags, libs)

    bin_name = os.environ.get('UWSGI_BIN_NAME', uc.get('bin_name'))

    if uc.get('embed_config'):
        gcc_list.append(uc.get('embed_config'))
    for ef in binary_list:
        gcc_list.append("build/%s" % ef)

    print("*** uWSGI linking ***")
    ldline = "%s -o %s %s %s %s" % (GCC, bin_name, ' '.join(uniq_warnings(ldflags)),
        ' '.join(map(add_o, gcc_list)), ' '.join(uniq_warnings(libs)))
    print(ldline)
    ret = os.system(ldline)
    if ret != 0:
        print("*** error linking uWSGI ***")
        sys.exit(1)

    if bin_name.find("/") < 0:
        bin_name = './' + bin_name
    if uc.get('as_shared_library'):
        print("*** uWSGI shared library (%s) is ready, move it to a library directory ***" % bin_name)
    else:
        print("*** uWSGI is ready, launch it with %s ***" % bin_name)


class uConf(object):

    def __init__(self, filename, mute=False):
        self.config = ConfigParser.ConfigParser()
        if not mute:
            print("using profile: %s" % filename)
        if not os.path.exists(filename):
            raise Exception("profile not found !!!")

        if os.path.exists('uwsgibuild.lastprofile'):
            ulp = open('uwsgibuild.lastprofile','r')
            last_profile = ulp.read()
            ulp.close()
            if last_profile != filename:
                os.environ['UWSGI_FORCE_REBUILD'] = '1'

        ulp = open('uwsgibuild.lastprofile','w')
        ulp.write(filename)
        ulp.close()

        self.config.read(filename)
        self.gcc_list = ['utils', 'protocol', 'socket', 'logging', 'master', 'master_utils', 'emperor', 'notify', 'mule', 'subscription', 'stats',
            'plugins', 'lock', 'cache', 'queue', 'event', 'signal', 'cluster', 'rpc', 'gateway', 'loop', 'lib/rbtree', 'lib/amqp', 'rb_timers', 'uwsgi']
        # add protocols
        self.gcc_list.append('proto/base')
        self.gcc_list.append('proto/uwsgi')
        self.gcc_list.append('proto/http')
        self.gcc_list.append('proto/fastcgi')
        self.include_path = []

        self.cflags = ['-O2', '-Wall', '-Werror', '-D_LARGEFILE_SOURCE', '-D_FILE_OFFSET_BITS=64'] + os.environ.get("CFLAGS", "").split()

        if uwsgi_os == 'Linux':
            self.gcc_list.append('lib/linux_ns')
            try:
                lk_ver = uwsgi_os_k.split('.')
                if int(lk_ver[0]) <= 2 and int(lk_ver[1]) <= 6 and int(lk_ver[2]) <= 9:
                    self.cflags.append('-DOBSOLETE_LINUX_KERNEL')                    
            except:
                pass

        try:
            gcc_version = str(spcall("%s -dumpversion" % GCC))
        except:
            print("*** you need a c compiler to build uWSGI ***")
            sys.exit(1)

        try:
            add_it = False
            cpp_include_list = str(spcall3("%s -v" % CPP)).split("\n")
            for line in cpp_include_list:
                if line.startswith('#include <...> search starts here:'):
                    add_it = True
                elif line.startswith('End of search list.'):
                    add_it = False
                elif add_it:
                    self.include_path.append(line.strip().split()[0])
            
            if not self.include_path:
                raise 
        except:
            self.include_path = ['/usr/include', '/usr/local/include']

        additional_include_paths = self.get('additional_include_paths')
        if additional_include_paths:
            for ipath in additional_include_paths.split():
                self.include_path.append(ipath)
            
        if not mute:
            print("detected include path: %s" % self.include_path)

        try:
            gcc_major = int(gcc_version.split('.')[0])
            gcc_minor = int(gcc_version.split('.')[1])
        except:
            raise Exception("you need a C compiler to build uWSGI")
        if (sys.version_info[0] == 2) or (gcc_major < 4) or (gcc_major == 4 and gcc_minor < 3):
            self.cflags = self.cflags + ['-fno-strict-aliasing']
        # add -fno-strict-aliasing only on python2 and gcc < 4.3
        if gcc_major >= 4:
            self.cflags = self.cflags + [ '-Wextra', '-Wno-unused-parameter', '-Wno-missing-field-initializers' ]

        self.ldflags = os.environ.get("LDFLAGS", "").split()
        self.libs = ['-lpthread', '-lm', '-rdynamic']
        if uwsgi_os == 'Linux':
            self.libs.append('-ldl')

        # check for inherit option
        inherit = self.get('inherit')
        if inherit:
            if not '/' in inherit:
                inherit = 'buildconf/%s' % inherit

            if not inherit.endswith('.ini'):
                inherit = '%s.ini' % inherit

            interpolations = {}
            for option in self.config.options('uwsgi'):
                interpolations[option] = self.get(option)
            iconfig = ConfigParser.ConfigParser(interpolations)
            iconfig.read(inherit)
            for opt in iconfig.options('uwsgi'):
                if not self.config.has_option('uwsgi', opt):
                    self.set(opt, iconfig.get('uwsgi', opt))
                elif self.get(opt):
                    if self.get(opt).startswith('+'):
                        self.set(opt, iconfig.get('uwsgi', opt) + self.get(opt)[1:])
                    elif self.get(opt) == 'null':
                        self.config.remove_option('uwsgi', opt)


    def set(self, key, value):
        self.config.set('uwsgi',key, value)

    def get(self,key,default=None):
        try:
            value = self.config.get('uwsgi', key)
            if value == "" or value == "false":
                return None
            return value
        except:
            if default:
                return default
            return None

    def depends_on(self, what, dep):
        for d in dep:
            if not self.get(d):
                print("%s needs %s support." % (what, d))
                sys.exit(1)

    def has_include(self, what):
        for include in self.include_path:
            if os.path.exists("%s/%s" %(include, what)):
                return True
        return False

    def get_gcll(self):

        global uwsgi_version

        self.cflags.append('-DUWSGI_BUILD_DATE="\\"%s\\""' % time.strftime("%d %B %Y %H:%M:%S"))
        kvm_list = ['FreeBSD', 'OpenBSD', 'NetBSD', 'DragonFly']

        if self.has_include('ifaddrs.h'):
            self.cflags.append('-DUWSGI_HAS_IFADDRS')

        if uwsgi_os in ('FreeBSD', 'OpenBSD'):
            if self.has_include('execinfo.h') or os.path.exists('/usr/local/include/execinfo.h'):
                if os.path.exists('/usr/local/include/execinfo.h'):
                    self.cflags.append('-I/usr/local/include')
                    self.ldflags.append('-L/usr/local/lib')
                self.cflags.append('-DUWSGI_HAS_EXECINFO')
                self.libs.append('-lexecinfo')

        if uwsgi_os == 'OpenBSD':
            try:
                obsd_major = int(uwsgi_os_k.split('.')[0])
                obsd_minor = int(uwsgi_os_k.split('.')[1])
                if obsd_major >= 5 and obsd_minor > 0:
                    self.cflags.append('-DUWSGI_NEW_OPENBSD')
            except:
                pass

        if uwsgi_os == 'SunOS':
            self.libs.append('-lsendfile')
            self.gcc_list.append('lib/sun_fixes')
            self.ldflags.append('-L/lib')
            if not uwsgi_os_v.startswith('Nexenta'):
                self.libs.remove('-rdynamic')

        if uwsgi_os in kvm_list:
            self.libs.append('-lkvm')

        if uwsgi_os == 'Haiku':
            self.set('async', 'false')
            self.libs.remove('-rdynamic')
            self.libs.remove('-lpthread')
            self.libs.append('-lroot')

        if uwsgi_os == 'Darwin':
            self.cflags.append('-mmacosx-version-min=10.5')

        # compile extras
        extras = self.get('extras', None)
        if extras:
            for extra in extras.split(','):
                self.gcc_list.append(extra)

        # set locking subsystem
        locking_mode = self.get('locking','auto')

        if locking_mode == 'auto':
            if uwsgi_os == 'Linux' or uwsgi_os == 'SunOS':
                locking_mode = 'pthread_mutex'
            # FreeBSD umtx is still not ready for process shared locking
            # starting from FreeBSD 9 posix semaphores can be shared between processes
            elif uwsgi_os == 'FreeBSD':
                 try:
                     fbsd_major = int(uwsgi_os_k.split('.')[0])
                     if fbsd_major >= 9:
                         locking_mode = 'posix_sem'
                 except:
                     pass
            elif uwsgi_os == 'Darwin':
                locking_mode = 'osx_spinlock'

        if locking_mode == 'pthread_mutex':
            self.cflags.append('-DUWSGI_LOCK_USE_MUTEX')
        # FreeBSD umtx is still not ready for process shared locking
        elif locking_mode == 'posix_sem':
            self.cflags.append('-DUWSGI_LOCK_USE_POSIX_SEM')
        elif locking_mode == 'osx_spinlock':
            self.cflags.append('-DUWSGI_LOCK_USE_OSX_SPINLOCK')

        # set event subsystem
        event_mode = self.get('event','auto')

        if event_mode == 'auto':
            if uwsgi_os == 'Linux':
                event_mode = 'epoll'
            if uwsgi_os == 'SunOS':
                event_mode = 'devpoll'
                sun_major, sun_minor = uwsgi_os_k.split('.')
                if int(sun_major) >= 5:
                    if int(sun_minor) >= 10:
                        event_mode = 'port'
            elif uwsgi_os in ('Darwin', 'FreeBSD', 'OpenBSD', 'NetBSD'):
                event_mode = 'kqueue'

        if event_mode == 'epoll':
            self.cflags.append('-DUWSGI_EVENT_USE_EPOLL')
        elif event_mode == 'kqueue':
            self.cflags.append('-DUWSGI_EVENT_USE_KQUEUE')
        elif event_mode == 'devpoll':
            self.cflags.append('-DUWSGI_EVENT_USE_DEVPOLL')
        elif event_mode == 'port':
            self.cflags.append('-DUWSGI_EVENT_USE_PORT')

        # set timer subsystem
        timer_mode = self.get('timer','auto')

        if timer_mode == 'auto':
            if uwsgi_os == 'Linux':
                k_all = uwsgi_os_k.split('.')
                k_base = k_all[0]
                k_major = k_all[1]
                if len(k_all) > 2:
                    k_minor = k_all[2]
                else:
                    k_minor = 0
                if int(k_base) > 2:
                    timer_mode = 'timerfd'
                elif int(k_minor) >= 25:
                    timer_mode = 'timerfd'
                else:
                    timer_mode = 'none'

            elif uwsgi_os == 'SunOS':
                sun_major, sun_minor = uwsgi_os_k.split('.')
                if int(sun_major) >= 5:
                    if int(sun_minor) >= 10:
                        timer_mode = 'port'

            elif uwsgi_os in ('Darwin', 'FreeBSD'):
                timer_mode = 'kqueue'

        if timer_mode == 'timerfd':
            self.cflags.append('-DUWSGI_EVENT_TIMER_USE_TIMERFD')
            if not self.has_include('sys/timerfd.h'):
                self.cflags.append('-DUWSGI_EVENT_TIMER_USE_TIMERFD_NOINC')
        elif timer_mode == 'kqueue':
            self.cflags.append('-DUWSGI_EVENT_TIMER_USE_KQUEUE')
        elif timer_mode == 'port':
            self.cflags.append('-DUWSGI_EVENT_TIMER_USE_PORT')
        else:
            self.cflags.append('-DUWSGI_EVENT_TIMER_USE_NONE')

        # set filemonitor subsystem
        filemonitor_mode = self.get('filemonitor','auto')

        if filemonitor_mode == 'auto':
            if uwsgi_os == 'Linux':
                filemonitor_mode = 'inotify'
            elif uwsgi_os == 'SunOS':
                sun_major, sun_minor = uwsgi_os_k.split('.')
                if int(sun_major) >= 5:
                    if int(sun_minor) >= 10:
                        filemonitor_mode = 'port'
            elif uwsgi_os in ('Darwin', 'FreeBSD'):
                filemonitor_mode = 'kqueue'

        if filemonitor_mode == 'inotify':
            self.cflags.append('-DUWSGI_EVENT_FILEMONITOR_USE_INOTIFY')
        elif filemonitor_mode == 'kqueue':
            self.cflags.append('-DUWSGI_EVENT_FILEMONITOR_USE_KQUEUE')
        elif filemonitor_mode == 'port':
            self.cflags.append('-DUWSGI_EVENT_FILEMONITOR_USE_PORT')
        else:
            self.cflags.append('-DUWSGI_EVENT_FILEMONITOR_USE_NONE')


        if self.get('malloc_implementation') != 'libc':
            if self.get('malloc_implementation') == 'tcmalloc':
                self.libs.append('-ltcmalloc')
            if self.get('malloc_implementation') == 'jemalloc':
                self.libs.append('-ljemalloc')

        if self.get('as_shared_library'):
            self.ldflags.append('-shared')
            self.ldflags.append('-fPIC')
            self.cflags.append('-DUWSGI_AS_SHARED_LIBRARY')
            if uwsgi_os == 'Darwin':
                self.ldflags.append('-dynamiclib')
                self.ldflags.append('-undefined dynamic_lookup')

        if self.get('embedded'):
            self.cflags.append('-DUWSGI_EMBEDDED')

        if self.get('udp'):
            self.cflags.append("-DUWSGI_UDP")

        if self.get('blacklist'):
            self.cflags.append('-DUWSGI_BLACKLIST="\\"%s\\""' % self.get('blacklist'))

        if self.get('whitelist'):
            self.cflags.append('-DUWSGI_WHITELIST="\\"%s\\""' % self.get('whitelist'))

        has_pcre = False

        # re-enable after pcre fix
        if self.get('pcre'):
            if self.get('pcre') == 'auto':
                pcreconf = spcall('pcre-config --libs')
                if pcreconf:
                    self.libs.append(pcreconf)
                    pcreconf = spcall("pcre-config --cflags")
                    self.cflags.append(pcreconf)
                    self.gcc_list.append('regexp')
                    self.cflags.append("-DUWSGI_PCRE")
                    has_pcre = True

            else:
                pcreconf = spcall('pcre-config --libs')
                if pcreconf is None:
                    print("*** libpcre headers unavailable. uWSGI build is interrupted. You have to install pcre development package or disable pcre")
                    sys.exit(1)
                else:
                    self.libs.append(pcreconf)
                    pcreconf = spcall("pcre-config --cflags")
                    self.cflags.append(pcreconf)
                    self.gcc_list.append('regexp')
                    self.cflags.append("-DUWSGI_PCRE")
                    has_pcre = True

        if self.get('routing'):
            if self.get('pcre') == 'auto':
                if has_pcre:
                    self.gcc_list.append('routing')
                    self.cflags.append("-DUWSGI_ROUTING") 
            else:
                self.gcc_list.append('routing')
                self.cflags.append("-DUWSGI_ROUTING")


        if self.has_include('sys/capability.h') and uwsgi_os == 'Linux':
            self.cflags.append("-DUWSGI_CAP")
            self.libs.append('-lcap')

        has_json = False
        has_uuid = False

        if self.has_include('uuid/uuid.h'):
            has_uuid = True
            self.cflags.append("-DUWSGI_UUID")
            if uwsgi_os == 'Linux' or os.path.exists('/usr/lib/libuuid.so') or os.path.exists('/usr/local/lib/libuuid.so') or os.path.exists('/usr/lib64/libuuid.so') or os.path.exists('/usr/local/lib64/libuuid.so'):
                self.libs.append('-luuid')

        if self.get('append_version'):
            if not self.get('append_version').startswith('-'):
                uwsgi_version += '-'
            uwsgi_version += self.get('append_version')



        if uwsgi_os == 'Linux':
            if self.get('embed_config'):
                binary_link_cmd = "ld -r -b binary -o %s.o %s" % (self.get('embed_config'), self.get('embed_config'))
                print(binary_link_cmd)
                os.system(binary_link_cmd)
                self.cflags.append("-DUWSGI_EMBED_CONFIG=_binary_%s_start" % self.get('embed_config').replace('.','_'))
                self.cflags.append("-DUWSGI_EMBED_CONFIG_END=_binary_%s_end" % self.get('embed_config').replace('.','_'))
            if self.get('embed_files'):
                for ef in self.get('embed_files').split(','):
                    ef_parts = ef.split('=')
                    symbase = None
                    if len(ef_parts) > 1:
                        ef = ef_parts[1]
                        symbase = ef_parts[0]
                    if os.path.isdir(ef):
                        for directory, directories, files in os.walk(ef):
                            for f in files:
                                fname = "%s/%s" % (directory, f)
                                binary_link_cmd = "ld -r -b binary -o build/%s.o %s" % (binarize(fname), fname)
                                print(binary_link_cmd)
                                os.system(binary_link_cmd)
                                if symbase:
                                    for kind in ('start','end'):
                                        objcopy_cmd = "objcopy --redefine-sym _binary_%s_%s=_binary_%s%s_%s build/%s.o" % (binarize(fname), kind, binarize(symbase), binarize(fname[len(ef):]), kind, binarize(fname))
                                        print(objcopy_cmd)
                                        os.system(objcopy_cmd)
                                binary_list.append(binarize(fname))
                    else:
                        binary_link_cmd = "ld -r -b binary -o build/%s.o %s" % (binarize(ef), ef)
                        print(binary_link_cmd)
                        os.system(binary_link_cmd)
                        binary_list.append(binarize(ef))
                        if symbase:
                            for kind in ('start','end'):
                                objcopy_cmd = "objcopy --redefine-sym _binary_%s_%s=_binary_%s_%s build/%s.o" % (binarize(ef), kind, binarize(symbase), kind, binarize(ef))
                                print(objcopy_cmd)
                                os.system(objcopy_cmd)
                
                 

        self.cflags.append('-DUWSGI_VERSION="\\"' + uwsgi_version + '\\""')

        uver_whole = uwsgi_version.split('-', 1)
        if len(uver_whole) == 1:
            uver_custom = ''
        else:
            uver_custom = uver_whole[1]

        uver_dots = uver_whole[0].split('.')

        uver_base = uver_dots[0]
        uver_maj = uver_dots[1]
        uver_min = '0'
        uver_rev = '0'

        if len(uver_dots) > 2:
            uver_min = uver_dots[2]

        if len(uver_dots) > 3:
            uver_rev = uver_dots[3]
        

        self.cflags.append('-DUWSGI_VERSION_BASE="' + uver_base + '"')
        self.cflags.append('-DUWSGI_VERSION_MAJOR="' + uver_maj + '"')
        self.cflags.append('-DUWSGI_VERSION_MINOR="' + uver_min + '"')
        self.cflags.append('-DUWSGI_VERSION_REVISION="' + uver_rev + '"')
        self.cflags.append('-DUWSGI_VERSION_CUSTOM="\\"' + uver_custom + '\\""')

	

        if self.get('async'):
            self.cflags.append("-DUWSGI_ASYNC")
            self.gcc_list.append('async')

        if self.get('multicast'):
            self.depends_on('multicast', ['udp'])
            self.cflags.append("-DUWSGI_MULTICAST")

        if self.get('minterpreters'):
            self.cflags.append("-DUWSGI_MINTERPRETERS")

        if self.get('ini'):
            self.cflags.append("-DUWSGI_INI")
            self.gcc_list.append('ini')

        if self.get('yaml'):
            self.cflags.append("-DUWSGI_YAML")
            self.gcc_list.append('yaml')
            if self.get('yaml_implementation') == 'libyaml':
                self.cflags.append("-DUWSGI_LIBYAML")
                self.libs.append('-lyaml')
            if self.get('yaml_implementation') == 'auto':
                if self.has_include('yaml.h'):
                    self.cflags.append("-DUWSGI_LIBYAML")
                    self.libs.append('-lyaml')

        if self.get('json'):
            if self.get('json') == 'auto':
                jsonconf = spcall("pkg-config --cflags jansson")
                if jsonconf:
                    self.cflags.append(jsonconf)
                    self.cflags.append("-DUWSGI_JSON")
                    self.gcc_list.append('json')
                    self.libs.append(spcall("pkg-config --libs jansson"))
                    has_json = True
                elif self.has_include('jansson.h'):
                    self.cflags.append("-DUWSGI_JSON")
                    self.gcc_list.append('json')
                    self.libs.append('-ljansson')
                    has_json = True
            else:
                self.cflags.append("-DUWSGI_JSON")
                self.gcc_list.append('json')
                self.libs.append('-ljansson')
                has_json = True

        if self.get('ldap'):
            if self.get('ldap') == 'auto':
                if self.has_include('ldap.h'):
                    self.cflags.append("-DUWSGI_LDAP")
                    self.gcc_list.append('ldap')
                    self.libs.append('-lldap')
            else:
                self.cflags.append("-DUWSGI_LDAP")
                self.gcc_list.append('ldap')
                self.libs.append('-lldap')

        if self.get('ssl'):
            if self.get('ssl') == 'auto':
                if self.has_include('openssl/ssl.h'):
                    self.cflags.append("-DUWSGI_SSL")
                    self.libs.append('-lssl')
                    self.libs.append('-lcrypto')
            else:
                self.cflags.append("-DUWSGI_SSL")
                self.libs.append('-lcrypto')


        if self.get('sctp'):
            if self.get('sctp') == 'auto':
                if self.has_include('netinet/sctp.h'):
                    if os.path.exists('/usr/lib/libsctp.so') or os.path.exists('/usr/local/lib/libsctp.so') or os.path.exists('/usr/lib64/libsctp.so') or os.path.exists('/usr/local/lib64/libsctp.so'):
                        self.gcc_list.append('proto/sctp')
                        self.cflags.append("-DUWSGI_SCTP")
                        self.libs.append('-lsctp')
            else:
                self.gcc_list.append('proto/sctp')
                self.cflags.append("-DUWSGI_SCTP")
                self.libs.append('-lsctp')

        if has_uuid and self.get('zeromq'):
            if self.get('zeromq') == 'auto':
                if self.has_include('zmq.h'):
                    self.cflags.append("-DUWSGI_ZEROMQ")
                    self.gcc_list.append('proto/zeromq')
                    self.libs.append('-lzmq')
            else:
                self.cflags.append("-DUWSGI_ZEROMQ")
                self.gcc_list.append('proto/zeromq')
                self.libs.append('-lzmq')

        if self.get('evdis'):
            self.cflags.append("-DUWSGI_EVDIS")
            self.gcc_list.append('evdis')

        if self.get('snmp'):
            self.depends_on("snmp", ['udp'])
            self.cflags.append("-DUWSGI_SNMP")
            self.gcc_list.append('snmp')

        if self.get('threading'):
            self.cflags.append("-DUWSGI_THREADING")

        if self.get('sendfile'):
            self.cflags.append("-DUWSGI_SENDFILE")
            self.gcc_list.append('sendfile')

        if self.get('xml'):
            if self.get('xml') == 'auto':
                xmlconf = spcall('xml2-config --libs')
                if xmlconf:
                    self.libs.append(xmlconf)
                    xmlconf = spcall("xml2-config --cflags")
                    self.cflags.append(xmlconf)
                    self.cflags.append("-DUWSGI_XML -DUWSGI_XML_LIBXML2")
                    self.gcc_list.append('xmlconf')
                elif self.has_include('expat.h'):
                    self.cflags.append("-DUWSGI_XML -DUWSGI_XML_EXPAT")
                    self.libs.append('-lexpat')
                    self.gcc_list.append('xmlconf')
            elif self.get('xml_implementation') == 'libxml2':
                xmlconf = spcall('xml2-config --libs')
                if xmlconf is None:
                    print("*** libxml2 headers unavailable. uWSGI build is interrupted. You have to install libxml2 development package or use libexpat or disable XML")
                    sys.exit(1)
                else:
                    self.libs.append(xmlconf)
                    xmlconf = spcall("xml2-config --cflags")
                    if xmlconf is None:
                        print("*** libxml2 headers unavailable. uWSGI build is interrupted. You have to install libxml2 development package or use libexpat or disable XML")
                        sys.exit(1)
                    else:
                        self.cflags.append(xmlconf)
                        self.cflags.append("-DUWSGI_XML -DUWSGI_XML_LIBXML2")
                        self.gcc_list.append('xmlconf')
            elif self.get('xml_implementation') == 'expat':
                self.cflags.append("-DUWSGI_XML -DUWSGI_XML_EXPAT")
                self.libs.append('-lexpat')
                self.gcc_list.append('xmlconf')

        if self.get('sqlite3'):
            if self.get('sqlite3') == 'auto':
                if self.has_include('sqlite3.h'):
                    self.cflags.append("-DUWSGI_SQLITE3")
                    self.libs.append('-lsqlite3')
                    self.gcc_list.append('sqlite3')
            else:
                self.cflags.append("-DUWSGI_SQLITE3")
                self.libs.append('-lsqlite3')
                self.gcc_list.append('sqlite3')


        if self.get('plugin_dir'):
            self.cflags.append('-DUWSGI_PLUGIN_DIR=\\"%s\\"' % self.get('plugin_dir'))

        if self.get('spooler'):
            self.depends_on("spooler", ['embedded'])
            self.cflags.append("-DUWSGI_SPOOLER")
            self.gcc_list.append('spooler')

        if self.get('debug'):
            self.cflags.append("-DUWSGI_DEBUG")
            self.cflags.append("-g")

        if self.get('unbit'):
            self.cflags.append("-DUNBIT")

        return self.gcc_list, self.cflags, self.ldflags, self.libs

def build_plugin(path, uc, cflags, ldflags, libs, name = None):
    path = path.rstrip('/')

    sys.path.insert(0, path)
    import uwsgiplugin as up
    reload(up)

    p_cflags = cflags[:]
    p_ldflags = ldflags[:]

    p_cflags += up.CFLAGS
    p_ldflags += up.LDFLAGS
    p_libs = up.LIBS

    p_cflags.insert(0, '-I.')

    if name is None:
        name = up.NAME
    else:
        p_cflags.append("-D%s_plugin=%s_plugin" % (up.NAME, name))

    try:
        for opt in uc.config.options(name):
            p_cflags.append('-DUWSGI_PLUGIN_%s_%s="%s"' % (name.upper(), opt.upper(), uc.config.get(name, opt, '1')))
    except:
        pass

    plugin_dest = uc.get('plugin_dir') + '/' + name + '_plugin'

    shared_flag = '-shared'

    gcc_list = []

    if uwsgi_os == 'Darwin':
        shared_flag = '-dynamiclib -undefined dynamic_lookup'

    for cfile in up.GCC_LIST:
        if cfile.endswith('.a'): 
            gcc_list.append(cfile)
        elif not cfile.endswith('.c') and not cfile.endswith('.cc'):
            gcc_list.append(path + '/' + cfile + '.c')
        else:
            gcc_list.append(path + '/' + cfile)

    try:
        p_ldflags.remove('-Wl,--no-undefined')
    except:
        pass

    try:
        p_cflags.remove('-Wwrite-strings')
    except:
        pass

    try:
        p_cflags.remove('-Werror=write-strings')
    except:
        pass

    try:
        p_cflags.remove('-Wdeclaration-after-statement')
    except:
        pass

    try:
        p_cflags.remove('-Werror=declaration-after-statement')
    except:
        pass

    try:
        p_cflags.remove('-Winline')
    except:
        pass


    #for ofile in up.OBJ_LIST:
    #    gcc_list.insert(0,ofile)

    gccline = "%s -fPIC %s -o %s.so %s %s %s %s" % (GCC, shared_flag, plugin_dest, ' '.join(uniq_warnings(p_cflags)), ' '.join(gcc_list), ' '.join(uniq_warnings(p_ldflags)), ' '.join(uniq_warnings(p_libs)) )
    print("[%s] %s.so" % (GCC, plugin_dest))

    ret = os.system(gccline)
    if ret != 0:
        print("*** unable to build %s plugin ***" % name)
        sys.exit(1)

    print("*** %s plugin built and available in %s ***" % (name, plugin_dest + '.so'))

if __name__ == "__main__":
    try:
        cmd = sys.argv[1]
    except:
        print("please specify an argument")
        sys.exit(1)

    if cmd == '--build':
        bconf = os.environ.get('UWSGI_PROFILE','default.ini')
        try:
            bconf = sys.argv[2]
        except:
            pass
        if not bconf.endswith('.ini'):
            bconf += '.ini'
        if not '/' in bconf:
            bconf = 'buildconf/%s' % bconf
        build_uwsgi(uConf(bconf))
    elif cmd == '--cflags':
        bconf = os.environ.get('UWSGI_PROFILE','default.ini')
        try:
            bconf = sys.argv[2]
        except:
            pass
        if not bconf.endswith('.ini'):
            bconf += '.ini'
        if not '/' in bconf:
            bconf = 'buildconf/%s' % bconf
        build_uwsgi(uConf(bconf, True), True)
    elif cmd == '--unbit':
        build_uwsgi(uConf('buildconf/unbit.ini'))
    elif cmd == '--plugin':
        bconf = os.environ.get('UWSGI_PROFILE','default.ini')
        try:
            bconf = sys.argv[3]
            if not bconf.endswith('.ini'):
                bconf += '.ini'
        except:
            pass
        if not '/' in bconf:
            bconf = 'buildconf/%s' % bconf
        uc = uConf(bconf)
        gcc_list, cflags, ldflags, libs = uc.get_gcll()
        try:
            name = sys.argv[4]
        except:
            name = None
        print("*** uWSGI building and linking plugin %s ***" % sys.argv[2] )
        build_plugin(sys.argv[2], uc, cflags, ldflags, libs, name)
    elif cmd == '--clean':
        os.system("rm -f *.o")
        os.system("rm -f proto/*.o")
        os.system("rm -f lib/*.o")
        os.system("rm -f plugins/*/*.o")
        os.system("rm -f build/*.o")

    else:
        print("unknown uwsgiconfig command")
        sys.exit(1)
