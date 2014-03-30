import sublime
import os
import signal, subprocess
import json
from hashlib import sha1 

if int(sublime.version()) >= 3000:
    from .base_command import BaseCommand
else:
    from base_command import BaseCommand
    
class GulpCommand(BaseCommand):
    package_name = "Gulp"
    cache_file_name = ".sublime-gulp.cache"
    
    def work(self):
        self.set_instance_variables()
        self.list_gulp_files()

    def set_instance_variables(self):
        self.gulp_files = []
        self.env = Env(self.settings)

    def list_gulp_files(self):
        self.folders = []
        for folder_path in self.window.folders():
            self.folders.append(folder_path)
            self.append_to_gulp_files(folder_path)
        if len(self.gulp_files) > 0:
            self.choose_file()
        else:
            sublime.error_message("gulpfile.js or gulpfile.coffee not found!")

    def append_to_gulp_files(self, path):
        if os.path.exists(os.path.join(path, "gulpfile.js")):
            self.gulp_files.append(os.path.join(path, "gulpfile.js"))
        elif os.path.exists(os.path.join(path, "gulpfile.coffee")):
            self.gulp_files.append(os.path.join(path, "gulpfile.coffee"))

    def choose_file(self):
        if len(self.gulp_files) == 1:
            self.show_tasks_from_gulp_file(0)
        else:
            self.window.show_quick_panel(self.gulp_files, self.show_tasks_from_gulp_file)

    def show_tasks_from_gulp_file(self, file_index):
        if file_index > -1:
            self.working_dir = os.path.dirname(self.gulp_files[file_index])
            self.tasks = self.list_tasks()
            if self.tasks is not None:
                self.show_quick_panel(self.tasks, self.run_gulp_task)

    def list_tasks(self):
        try:
            self.callcount = 0
            json_result = self.fetch_json()
        except TypeError as e:
            sublime.error_message("SublimeGulp: JSON  cache (.sublime-gulp.cache) is malformed.\nCould not read available tasks\n")
        else:
            tasks = [[name, self.dependencies_text(task)] for name, task in json_result.items()]
            return sorted(tasks, key = lambda task: task)

    def dependencies_text(self, task):
        return "Dependencies: " + task['dependencies'] if task['dependencies'] else ""

    # Refactor
    def fetch_json(self):
        jsonfilename = os.path.join(self.working_dir, self.cache_file_name)
        gulpfile = os.path.join(self.working_dir, "gulpfile.js") # .coffee ?
        data = None

        if os.path.exists(jsonfilename):
            filesha1 = Security.hashfile(gulpfile)
            json_data = open(jsonfilename)

            try:
                data = json.load(json_data)
                if data[gulpfile]["sha1"] == filesha1:
                    return data[gulpfile]["tasks"]
            finally:
                json_data.close()

        self.callcount += 1

        if self.callcount == 1: 
            return self.write_to_cache()

        if data is None:
            raise TypeError("Could not write to cache gulpfile")

        raise TypeError("Sha1 from gulp cache ({0}) is not equal to calculated ({1})".format(data[gulpfile]["sha1"], filesha1))

    def write_to_cache(self):
        package_path = os.path.join(sublime.packages_path(), self.package_name)

        args = r'node %s/write_tasks_to_cache.js' % package_path # ST2?

        write_to_cache = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=self.env.get_path_with_exec_args(), cwd=self.working_dir, shell=True)
        (stdout, stderr) = write_to_cache.communicate()

        if 127 == write_to_cache.returncode:
            sublime.error_message("\"node\" command not found.\nPlease be sure to have node installed and in your PATH.")
            return

        return self.fetch_json()

    def run_gulp_task(self, task_index):
        sublime.set_timeout_async(lambda: self.__run__(task_index), 0)

    def __run__(self, task_index):
        if task_index > -1:
            cmd = r"gulp %s" % self.tasks[task_index][0],
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=self.env.get_path_with_exec_args(), cwd=self.working_dir, shell=True, preexec_fn=os.setsid)
            ProcessCache.add(process)
            self.show_process_output(process)

    def show_process_output(self, process):
        # ST2!
        self.show_output_panel("")
        for line in process.stdout:
            self.append_to_output_view(str(line.rstrip().decode('utf-8')) + "\n")
        process.terminate()


class GulpKillCommand(BaseCommand):
    def run(self):
        ProcessCache.each(self.kill)
        ProcessCache.clear()

    def kill(self, proc):
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            print("Process not found")

# This implementation still has problems
# 1. It isn't cross-platform
# 2. It queues tasks, so if watch is running and every other task will get executed after watch is killed
class ProcessCache():
    _procs = []

    @classmethod
    def add(cls, proc):
       cls._procs.append(proc)

    @classmethod
    def each(cls, fn):
        for proc in cls._procs:
            fn(proc)

    @classmethod
    def clear(cls):
        del cls._procs[:]

class Env():
    def __init__(self, settings):
        self.exec_args = settings.get('exec_args', False)

    def get_path(self):
        path = os.environ['PATH']
        if self.exec_args:
            path = exec_args.get('path', os.environ['PATH'])
        return str(path)

    def get_path_with_exec_args(self):
        env = os.environ.copy()
        if self.exec_args:
            path = str(exec_args.get('path', ''))
            if path:
                env['PATH'] = path
        return env

class Security():
    @classmethod
    def hashfile(cls, filename):
        with open(filename, mode='rb') as f:
            filehash = sha1()
            content = f.read();
            filehash.update(str("blob " + str(len(content)) + "\0").encode('UTF-8'))
            filehash.update(content)
            return filehash.hexdigest()
