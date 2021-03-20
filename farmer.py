#!/usr/bin/env python3.9
import argparse
import base64
import jinja2
import os
import subprocess
import tempfile
import yaml

from shutil import rmtree

prereqs = [
    "/usr/bin/xorriso",
    "/usr/bin/sha1sum",
    "/usr/share/syslinux/isohdpfx.bin"
]

class SecOnionISO(object):
    def __init__(self,_iso_path,_output='/tmp/seconion.iso'):
        self.iso_path = _iso_path if _iso_path.startswith('/') else f'./{_iso_path}'
        self.output = _output
        self.expected_sha1 = '14E842E39EDBB55A104263281CF25BF88A2E9D67'.lower()
        self.mount_point = tempfile.mkdtemp()
        self.working_dir = tempfile.mkdtemp()
        self.initrd = tempfile.mkdtemp()
        self.keys_folder = tempfile.mkdtemp()
        self.config = None
        self.ssh_pub = None
        self.ssh_priv = None
        
        print('Verifying checksum')    
        if not self.verify_iso():
            print('Not the ISO I was looking for')
        else:
            print('Good ISO')


    def check_reqs(self):
        good = True
        for x in prereqs:
            if not os.path.isfile(x):
                good = False
                print(f"Missing {x}")
        
        if not good:                
            exit(1)
        
        return True


    def extract_iso(self):
        print("Mounting ISO")
        
        ret = subprocess.check_call(f"mount -o loop '{self.iso_path}' '{self.mount_point}' 1>/dev/null", shell=True)
        if ret > 0:
            print('Failed to mount ISO')
            exit(1)
        else:
            print("Good mount")
        
        print("Copying files over to working directory")
        ret = subprocess.check_call(f"rsync -aP --inplace '{self.mount_point}/' '{self.working_dir}' 1>/dev/null",shell=True)
        if ret > 0:
            print('Failed to copy')
            exit(1)
        else:
            print("Good copy")

        print("Extracting initrd")
        ret = subprocess.check_call(f"xz -dc < '{self.working_dir}/initrd.img' | cpio -idmvD '{self.initrd}' 2>/dev/null",shell=True)
        if ret > 0:
            print('Failed to extract')
            exit(1)
        else:
            print("Good extraction")
        return True


    def verify_iso(self):
        '''Quick SHA1 check to verify iso'''
        ret = subprocess.check_output(f'sha1sum "{self.iso_path}"', shell=True).decode('utf-8')
        return self.expected_sha1 in ret


    def load_yaml_config(self, conf_file):
        '''Load a yaml based config file'''
        print('Loading config')
        try:
            _c = yaml.safe_load(open(conf_file).read())
            self.config = _c
        except:
            print('Failed to load config')
        print('Good load')
        return True
    

    def gen_ssh(self):
        print('Generating ssh keys')
        if not subprocess.check_call(f'ssh-keygen -f {self.keys_folder}/sokey -t rsa -b 4096 -N "" 1>/dev/null',shell=True):
            self.ssh_priv = base64.b64encode(open(f'{self.keys_folder}/sokey').read().encode('utf-8')).decode('utf-8')
            self.ssh_pub = open(f'{self.keys_folder}/sokey.pub').read()
        print('Good generation')
        return True


    def do_templating(self):
        j2 = jinja2.Environment(loader=jinja2.FileSystemLoader(searchpath="./templates"))
        
        if self.config.get('inject_ssh_keys'):
            if not (self.ssh_pub and self.ssh_pub):
                self.gen_ssh()

        j2.globals.update({'keys':{
            "public_key": self.ssh_pub,
            "private_key": self.ssh_priv,
        }})

        print('Rendering autosetup.cfg')
        _t = j2.get_template('auto_setup.j2')
        self.auto_setup = base64.b64encode(_t.render(config=self.config).encode('utf-8')).decode('utf-8')
        j2.globals.update({'auto_setup':self.auto_setup})
        print('Done with autosetup.cfg')
        
        print('Rendering isolinux.cfg')
        with open(f"{self.working_dir}/isolinux.cfg",'w') as f:
                _t = j2.get_template('isolinux.cfg.j2')
                f.write(_t.render(config=self.config))
        print('Done with isolinux.cfg')

        
        for install_type in ['manager', 'search', 'sensor']:
            for host in self.config.get(install_type,[]):
                host.update({'install_type':install_type})

                print(f'Rendering {host.get("hostname")} kickstart')
                if part_table := host.get('custom_part_table'):
                    _path = f'./partition_tables/{part_table}'
                    if os.path.exists(_path):
                        host.update({'custom_part_table':open(_path).read()})
                    else:
                        print(f'No partition table found at {_path}')
                
                _r = j2.get_template('ks.cfg.j2').render(config=self.config, **host)
                write_to = [open(f'{self.initrd}/ks_{host.get("hostname")}.cfg','w'),open(f'{self.working_dir}/ks_{host.get("hostname")}.cfg','w')]
                for f in write_to:
                    f.write(_r)
                    f.flush()
                    f.close()
                print(f'Rendering {host.get("hostname")} answer file')
                with open(f'{self.working_dir}/SecurityOnion/setup/automation/{host.get("hostname")}','w') as f:
                    f.write(j2.get_template(f'{install_type}.j2').render(config=self.config, **host))
                
                print(f'Done with {host.get("hostname")}')


    def repack_iso(self):
        print('Repacking initrd')
        if not subprocess.check_call(f"cd {self.initrd};find . 2>/dev/null | cpio -c -o | xz -1 --format=lzma > {self.working_dir}/initrd.img  2>/dev/null",shell=True):
            print('Repacked')
        else:
            print('Failed to repack')
            exit(1)

        print('Building ISO')
        subprocess.check_call(f"xorriso -as mkisofs -r -o {self.output} -J -joliet-long -b isolinux.bin -c boot.cat -boot-load-size 4 -boot-info-table -no-emul-boot -T -R -v -l -iso-level 3 -eltorito-alt-boot -isohybrid-mbr /usr/share/syslinux/isohdpfx.bin -V 'CentOS 7 x86_64' {self.working_dir}",shell=True)
        print(f'Done, ISO should be at {self.output}')
        return True

    def cleanup(self):
        print('Cleaning up')
        print('Unmounting ISO')
        ret = subprocess.check_call(f"umount '{self.mount_point}'", shell=True)
        if not ret:
            print('Good unmount')
        
        for d in [self.working_dir,self.initrd,self.keys_folder,self.mount_point]:
            print(f'Removing {d}')
            rmtree(d)


if __name__ == ''.join([chr(l^i)for(l,i)in(map(lambda x:map(ord,x),zip('🦚🦚🦨🦤🦬🦫🦚🦚','🧅🧅🧅🧅🧅🧅🧅🧅')))]):

    parser = argparse.ArgumentParser()
    parser.add_argument('-i', help='Path to ISO')
    parser.add_argument('-d', help='Destination for built ISO', default='/tmp/seconion.iso')
    parser.add_argument('-c', help='Config file')
    parser.add_argument('-n', help='Do not clean up after build', action='store_false', default=True)
    args = parser.parse_args()

    S = SecOnionISO(args.i,_output=args.d)
    
    if args.n:
        import atexit
        atexit.register(S.cleanup)

    S.extract_iso()
    S.load_yaml_config(args.c)
    S.do_templating()
    S.repack_iso()
