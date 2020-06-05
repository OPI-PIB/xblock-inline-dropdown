'''  Inline Dropdown XBlock main Python class'''

import pkg_resources
from django.template import Context, Template
from django.utils.translation import ungettext
from django.utils import translation
from django.utils.translation import ugettext_lazy

from xblock.core import XBlock
from xblock.fields import Scope, String, List, Float, Integer, Dict, Boolean
from xblock.fragment import Fragment
from xblockutils.resources import ResourceLoader

from lxml import etree
from xml.etree import ElementTree as ET
from xml.etree.ElementTree import Element, SubElement

from StringIO import StringIO

import textwrap
import operator

# from django.utils.translation import ugettext as _
_ = lambda text: text
loader = ResourceLoader(__name__)

@XBlock.needs('i18n')
class InlineDropdownXBlock(XBlock):
    '''
    Icon of the XBlock. Values : [other (default), video, problem]
    '''
    icon_class = 'problem'

    '''
    Fields
    '''
    display_name = String(
        display_name=_('Display Name'),
        default=_('Inline Dropdown'),
        scope=Scope.settings,
        help=_('This name appears in the horizontal navigation at the top of the page')
    )

    hints = List(
        default=[],
        scope=Scope.content,
        help=_('Hints for the question'),
    )

    question_string = String(
        help=_('Default question content '),
        scope=Scope.content,
        default=_('''
            <inline_dropdown schema_version='1'>
                <body>
                    <p>A fruit is the fertilized ovary of a tree or plant and contains seeds. Given this, a <input_ref input="i1"/> is consider a fruit, while a <input_ref input="i2"/> is considered a vegetable.</p>
                </body>
                <optionresponse>
                    <optioninput id="i1">
                        <option correct="True">tomato<optionhint>Since the tomato is the fertilized ovary of a tomato plant and contains seeds, it is a fruit.</optionhint></option>
                        <option correct="False">potato<optionhint>A potato is an edible part of a plant in tuber form and is a vegetable, not a fruit.</optionhint></option>
                    </optioninput>
                </optionresponse>
                <optionresponse>
                    <optioninput id="i2">
                        <option correct="True">onion<optionhint>The onion is the bulb of the onion plant and contains no seeds and is therefore a vegetable.</optionhint></option>
                        <option correct="False">cucumber<optionhint>Many people mistakenly think a cucumber is a vegetable. However, because a cucumber is the fertilized ovary of a cucumber plant and contains seeds, it is a fruit.</optionhint></option>
                    </optioninput>
                </optionresponse>
                <demandhint>
                    <hint>A fruit is the fertilized ovary from a flower.</hint>
                    <hint>A fruit contains seeds of the plant.</hint>
                </demandhint>
            </inline_dropdown>
        '''),
        # default=textwrap.dedent(str(default_question))
    )

    score = Float(
        default=0.0,
        scope=Scope.user_state,
    )

    correctness = Dict(
        help=_('Correctness of input values'),
        scope=Scope.user_state,
        default={},
    )

    selection_order = Dict(
        help=_('Order of selections in body'),
        scope=Scope.user_state,
        default={},
    )

    selections = Dict(
        help=_('Saved student input values'),
        scope=Scope.user_state,
        default={},
    )

    student_correctness = Dict(
        help=_('Saved student correctness values'),
        scope=Scope.user_state,
        default={},
    )

    feedback = Dict(
        help=_('Feedback for input values'),
        scope=Scope.user_state,
        default={},
    )

    current_feedback = String(
        help=_('Current feedback state'),
        scope=Scope.user_state,
        default='',
    )

    completed = Boolean(
        help=_('Indicates whether the learner has completed the problem at least once'),
        scope=Scope.user_state,
        default=False,
    )

    weight = Integer(
        display_name=_('Weight'),
        help=_(
            'This assigns an integer value representing '
            'the weight of this problem'
        ),
        default=2,
        scope=Scope.settings,
    )

    has_score = True
    skip_flag = False
    '''
    Main functions
    '''
    def student_view(self, context=None):
        '''
        The primary view of the XBlock, shown to students
        when viewing courses.
        '''
        self.init_emulation()
        frag = Fragment()
        attributes = ''
        i18n_ = self.runtime.service(self, "i18n").ugettext
        ctx = {
            'display_name': self.display_name,
            'problem_progress': self._get_problem_progress(),
            'prompt': self._get_body(self.question_string),
            'attributes': attributes
        }

        frag.add_content(loader.render_django_template(
            'static/html/inline_dropdown_view.html',
            context = ctx,
            i18n_service=self.runtime.service(self, "i18n"),
        ))

        frag.add_css(loader.load_unicode('static/css/inline_dropdown.css'))
        frag.add_javascript(loader.load_unicode('static/js/inline_dropdown_view.js'))
        frag.add_javascript(self.get_translation_content())
        frag.initialize_js('InlineDropdownXBlockInitView')
        return frag

    def studio_view(self, context=None):
        '''
        The secondary view of the XBlock, shown to teachers
        when editing the XBlock.
        '''
        self.init_emulation()
        frag = Fragment()
        ctx = {
            'display_name': self.display_name,
            'weight': self.weight,
            'xml_data': self.question_string,
        }
        frag.add_content(loader.render_django_template(
            'static/html/inline_dropdown_edit.html',
            context = ctx,
            i18n_service=self.runtime.service(self, "i18n"),
        ))
        frag.add_css(loader.load_unicode('static/css/inline_dropdown_edit.css'))
        # frag.add_javascript(self.get_translation_content())
        frag.add_javascript(loader.load_unicode('static/js/template_edit.js'))
        frag.add_javascript(loader.load_unicode('static/js/inline_dropdown_edit.js'))
        frag.initialize_js('InlineDropdownXBlockInitEdit')
        return frag

    def max_score(self):
        """
        Returns the configured number of possible points for this component.
        Arguments:
            None
        Returns:
            float: The number of possible points for this component
        """
        return self.weight if self.has_score else None

    @XBlock.json_handler
    def student_submit(self, submissions, suffix=''):
        '''
        Save student answer
        '''

        self.selections = submissions['selections']
        self.selection_order = submissions['selection_order']

        self.current_feedback = ''

        correct_count = 0
        i18n_ = self.runtime.service(self, "i18n").ugettext
        # use sorted selection_order to iterate through selections dict
        for key,pos in sorted(self.selection_order.iteritems(), key=lambda (k,v): (v,k)):
            selected_text = self.selections[key]

            if self.correctness[key][selected_text] == 'True':
                default_feedback = '<p class="correct"><strong>(' + str(pos) + ') ' + i18n_(_('Correct')) + '</strong></p>'
                if selected_text in self.feedback[key]:
                    if self.feedback[key][selected_text] is not None:
                        self.current_feedback += '<p class="correct"><strong>(' + str(pos) + ') ' + i18n_(_('Correct')) + ': </strong>' + self.feedback[key][selected_text] + '</p>'
                    else:
                        self.current_feedback += default_feedback
                else:
                    self.current_feedback += default_feedback
                self.student_correctness[key] = 'True'
                correct_count += 1
            else:
                default_feedback = '<p class="incorrect"><strong>(' + str(pos) + ') ' + i18n_(_('Incorrect')) + '</strong></p>'
                if selected_text in self.feedback[key]:
                    if self.feedback[key][selected_text] is not None:
                        self.current_feedback += '<p class="incorrect"><strong>(' + str(pos) + ') ' + i18n_(_('Incorrect')) + ': </strong>' + self.feedback[key][selected_text] + '</p>'
                    else:
                        self.current_feedback += default_feedback
                else:
                    self.current_feedback += default_feedback
                self.student_correctness[key] = 'False'

        self.score = float(self.weight) * correct_count / len(self.correctness)
        self._publish_grade()

        self.runtime.publish(self, 'dropdown_selected', {
            'selections': self.selections,
            'correctness': self.student_correctness,
        })
        self._publish_problem_check()

        self.completed = True

        result = {
            'success': True,
            'problem_progress': self._get_problem_progress(),
            'submissions': self.selections,
            'feedback': self.current_feedback,
            'correctness': self.student_correctness,
            'selection_order': self.selection_order,
        }
        return result

    @XBlock.json_handler
    def student_reset(self, submissions, suffix=''):
        '''
        Reset student answer
        '''

        self.score = 0.0
        self.current_feedback = ''
        self.selections = {}
        self.student_correctness = {}

        self._publish_grade()

        self.completed = False

        result = {
            'success': True,
            'problem_progress': self._get_problem_progress(),
        }
        return result

    @XBlock.json_handler
    def studio_submit(self, submissions, suffix=''):
        '''
        Save studio edits
        '''
        self.display_name = submissions['display_name']
        try:
            weight = int(submissions['weight'])
        except ValueError:
            weight = 0
        if weight > 0:
            self.weight = weight
        xml_content = submissions['data']

        try:
            etree.parse(StringIO(xml_content))
            self.question_string = xml_content
        except etree.XMLSyntaxError as e:
            return {
                'result': 'error',
                'message': e.message
            }

        return {
            'result': 'success',
        }

    @XBlock.json_handler
    def send_xblock_id(self, submissions, suffix=''):
        return {
            'result': 'success',
            'xblock_id': unicode(self.scope_ids.usage_id),
        }

    @XBlock.json_handler
    def restore_state(self, submissions, suffix=''):
        return {
            'result': 'success',
            'selections': self.selections,
            'correctness': self.student_correctness,
            'selection_order': self.selection_order,
            'current_feedback': self.current_feedback,
            'completed': self.completed,
        }

    @XBlock.json_handler
    def send_hints(self, submissions, suffix=''):
        i18n_ = self.runtime.service(self, "i18n").ugettext
        tree = etree.parse(StringIO(i18n_(self.question_string)))
        raw_hints = tree.xpath('/inline_dropdown/demandhint/hint')

        decorated_hints = list()

        if len(raw_hints) == 1:
            hint = i18n_(_('Hint')) + ': ' + etree.tostring(raw_hints[0], encoding='unicode')
            decorated_hints.append(hint)
        else:
            for i in range(len(raw_hints)):
                hint = i18n_(_('Hint')) + ' ({number} / {total}): {hint}'.format(
                    number=i + 1,
                    total=len(raw_hints),
                    hint=etree.tostring(raw_hints[i], encoding='unicode'))
                decorated_hints.append(hint)

        hints = decorated_hints

        return {
            'result': 'success',
            'hints': hints,
        }

    @XBlock.json_handler
    def publish_event(self, data, suffix=''):
        try:
            event_type = data.pop('event_type')
        except KeyError:
            return {'result': 'error', 'message': 'Missing event_type in JSON data'}

        data['user_id'] = self.scope_ids.user_id
        data['component_id'] = self._get_unique_id()
        self.runtime.publish(self, event_type, data)

        return {'result': 'success'}

    '''
    Util functions
    '''
    def load_resource(self, resource_path):
        '''
        Gets the content of a resource
        '''
        resource_content = pkg_resources.resource_string(__name__, resource_path)
        return unicode(resource_content)

    def render_template(self, template_path, context={}):
        '''
        Evaluate a template by resource path, applying the provided context
        '''
        template_str = self.load_resource(template_path)
        return Template(template_str).render(Context(context))

    def resource_string(self, path):
        '''Handy helper for getting resources from our kit.'''
        data = pkg_resources.resource_string(__name__, path)
        return data.decode('utf8')

    def _get_body(self, xmlstring):
        '''
        Helper method
        '''

        tree = etree.parse(StringIO(xmlstring))

        for input_ref in tree.iter('input_ref'):
            for optioninput in tree.iter('optioninput'):
                select = Element('select')
                valuecorrectness = dict()
                valuefeedback = dict()
                if optioninput.attrib['id'] == input_ref.attrib['input']:
                    newoption = SubElement(input_ref, 'option')
                    newoption.text = ''
                    for option in optioninput.iter('option'):
                        newoption = SubElement(input_ref, 'option')
                        newoption.text = option.text
                        valuecorrectness[option.text] = option.attrib['correct']
                        for optionhint in option.iter('optionhint'):
                            valuefeedback[option.text] = optionhint.text
                    input_ref.tag = 'select'
                    input_ref.attrib['xblock_id'] = unicode(self.scope_ids.usage_id)
                    self.correctness[optioninput.attrib['id']] = valuecorrectness
                    self.feedback[optioninput.attrib['id']] = valuefeedback


        body = tree.xpath('/inline_dropdown/body')

        bodystring = etree.tostring(body[0], encoding='unicode')

        return bodystring

    def _get_unique_id(self):
        try:
        	unique_id = self.location.name
        except AttributeError:
            # workaround for xblock workbench
            unique_id = 'workbench-workaround-id'
        return unique_id

    def _get_problem_progress(self):
        """
        Returns a statement of progress for the XBlock, which depends
        on the user's current score
        """
        i18n_ = self.runtime.service(self, "i18n").ungettext
        result = ''
        if self.score == 0.0:
            result = i18n_(
                '{weight} point possible',
                '{weight} points possible',
                self.weight,
            ).format(
                weight=self.weight)
        else:
            score_string = '{0:g}'.format(self.score)
            result = score_string + i18n_(
                "/{weight} point",
                "/{weight} points",
                self.weight
            ).format(
                weight=self.weight)

        return result

    def _publish_grade(self):
        self.runtime.publish(
            self,
            'grade',
            {
                'value': self.score,
                'max_value': self.weight,
            }
        )

    def _publish_problem_check(self):
        self.runtime.publish(
            self,
            'problem_check',
            {
                'grade': self.score,
                'max_grade': self.weight,
            }
        )

    def get_translation_content(self):
        try:
            return self.resource_string('static/js/translations/{lang}/text.js'.format(
                lang=translation.get_language(),
            ))
        except IOError:
            return self.resource_string('static/js/translations/en/text.js')

    def init_emulation(self):
        """
        Emulation of init function, for translation purpose.
        """
        if not self.skip_flag:
            i18n_ = self.runtime.service(self, "i18n").ugettext
            #     self.display_name = _(self.display_name)
            self.fields['display_name']._default = i18n_(self.fields['display_name']._default)
            self.fields['question_string']._default = i18n_(self.fields['question_string']._default)
            self.skip_flag = True

    @staticmethod
    def workbench_scenarios():
        """A canned scenario for display in the workbench."""
        return [
            ("InlineDropdownXBlock",
             """<inline-dropdown/>
             """),
            ("Multiple InlineDropdownXBlock",
             """<vertical_demo>
                <inline-dropdown/>
                <inline-dropdown/>
                <inline-dropdown/>
                </vertical_demo>
             """),
        ]

    @staticmethod
    def _get_statici18n_js_url():
        """
        Returns the Javascript translation file for the currently selected language, if any.
        Defaults to English if available.
        """
        locale_code = translation.get_language()
        if locale_code is None:
            return None
        text_js = 'public/js/translations/{locale_code}/text.js'
        lang_code = locale_code.split('-')[0]
        for code in (locale_code, lang_code, 'en'):
            loader = ResourceLoader(__name__)
            if pkg_resources.resource_exists(
                    loader.module_name, text_js.format(locale_code=code)):
                return text_js.format(locale_code=code)
        return None

    @staticmethod
    def get_dummy():
        """
        Dummy method to generate initial i18n
        """
        return translation.gettext_noop('Dummy')


