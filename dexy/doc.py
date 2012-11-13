import dexy.artifact
import dexy.exceptions
import dexy.filter
import dexy.task
import fnmatch
import os

class Doc(dexy.task.Task):
    ALIASES = ['doc']

    @classmethod
    def filter_class_for_alias(klass, alias):
        if alias == '':
            raise dexy.exceptions.BlankAlias
        elif alias.startswith("-"):
            return dexy.filter.DexyFilter
        else:
            try:
                return dexy.filter.Filter.aliases[alias]
            except KeyError:
                msg = "Dexy doesn't have a filter '%s' available." % alias

                all_plugins = dexy.filter.Filter.aliases.values()
                num_plugins = len(all_plugins)
                if num_plugins < 10:
                    plugin_list = ", ".join(p.__name__ for p in all_plugins)
                    msg += " Note that only %s plugins are available: %s" % (num_plugins, plugin_list)
                    msg += " There may be a problem loading plugins, adding 'import dexy.plugins' might help."

                raise dexy.exceptions.UserFeedback(msg)

    def output(self):
        """
        Returns a reference to the output_data Data object generated by the final filter.
        """
        final_state = self.final_artifact.state
        if not final_state == 'complete':
            if not final_state == 'setup' and len(self.filters) == 0:
                raise dexy.exceptions.InternalDexyProblem("Final artifact state is '%s'" % self.final_artifact.state)

        return self.final_artifact.output_data

    def setup_initial_artifact(self):
        if os.path.exists(self.name):
            initial = dexy.artifact.InitialArtifact(self.name, wrapper=self.wrapper)
        else:
            initial = dexy.artifact.InitialVirtualArtifact(self.name, wrapper=self.wrapper)

        initial.args = self.args
        initial.name = self.name
        initial.prior = None
        initial.doc = self
        initial.created_by_doc = self.created_by_doc
        initial.transition('populated')

        self.children.append(initial)
        self.artifacts.append(initial)
        self.final_artifact = initial

    def setup_filter_artifact(self, key, filters):
        artifact = dexy.artifact.FilterArtifact(key, wrapper=self.wrapper)

        # Remove args that are only relevant to the doc or to the initial artifact.
        filter_artifact_args = self.args.copy()
        for k in ['contents', 'contentshash', 'data-class-alias', 'depends']:
            if filter_artifact_args.has_key(k):
                del filter_artifact_args[k]

        artifact.args = filter_artifact_args

        artifact.doc = self
        artifact.filter_alias = filters[-1]
        artifact.doc_filepath = self.name
        artifact.prior = self.artifacts[-1]
        artifact.created_by_doc = self.created_by_doc
        artifact.transition('populated')

        try:
            artifact.filter_class = self.filter_class_for_alias(filters[-1])
        except dexy.exceptions.BlankAlias:
            raise dexy.exceptions.UserFeedback("You have a trailing | or you have 2 | symbols together in your specification for %s" % self.key)

        if not artifact.filter_class.is_active():
            raise dexy.exceptions.InactiveFilter(artifact.filter_alias, artifact.doc.key)

        artifact.filter_instance = artifact.filter_class()
        artifact.filter_instance.artifact = artifact
        artifact.set_log()
        artifact.filter_instance.log = artifact.log

        artifact.next_filter_alias = None
        artifact.next_filter_class = None
        artifact.next_filter_name = None

        if len(filters) < len(self.filters):
            next_filter_alias = self.filters[len(filters)]
            artifact.next_filter_alias = next_filter_alias
            artifact.next_filter_class = self.filter_class_for_alias(next_filter_alias)
            artifact.next_filter_name = artifact.next_filter_class.__name__

        self.children.append(artifact)
        self.artifacts.append(artifact)
        self.final_artifact = artifact

    def setup(self):
        self.hashstring = self.final_artifact.hashstring

    def metadata(self):
        return self.final_artifact.metadata

    def populate(self):
        self.set_log()
        self.name = self.key.split("|")[0]
        self.filters = self.key.split("|")[1:]
        self.artifacts = []
        self.canon = self.args.get('canon', len(self.filters) == 0)

        self.setup_initial_artifact()

        for i in range(0,len(self.filters)):
            filters = self.filters[0:i+1]
            key = "%s|%s" % (self.name, "|".join(filters))
            self.setup_filter_artifact(key, filters)
            self.canon = self.canon or (not self.final_artifact.filter_class.FRAGMENT)

class PatternDoc(dexy.task.Task):
    """
    A doc which takes a file matching pattern and creates individual Doc objects for all files that match the pattern.
    """
    ALIASES = ['pattern']

    def setup(self):
        self.hashstring = ''

    def populate(self):
        self.set_log()
        self.file_pattern = self.key.split("|")[0]
        self.filter_aliases = self.key.split("|")[1:]

        for dirpath, filename in self.wrapper.walk("."):
            raw_filepath = os.path.join(dirpath, filename)
            filepath = os.path.normpath(raw_filepath)

            if fnmatch.fnmatch(filepath, self.file_pattern):
                if len(self.filter_aliases) > 0:
                    doc_key = "%s|%s" % (filepath, "|".join(self.filter_aliases))
                else:
                    doc_key = filepath

                doc_args = self.args.copy()
                doc_args['wrapper'] = self.wrapper

                if doc_args.has_key('depends'):
                    if doc_args.get('depends'):
                        doc_children = self.wrapper.registered_docs()
                    else:
                        doc_children = []
                    del doc_args['depends']
                else:
                    doc_children = self.children

                doc = Doc(doc_key, *doc_children, **doc_args)
                self.children.append(doc)
                doc.populate()
                doc.transition('populated')

class BundleDoc(dexy.task.Task):
    """
    A doc which represents a collection of docs.
    """
    ALIASES = ['bundle']

    def populate(self):
        self.set_log()

    def setup(self):
        self.hashstring = ''
