import hpotk
import typing
import logging

from hpotk.validate import ValidationLevel

from genophenocorr.model import Phenotype

from ._audit import Auditor, Level, Notepad


class PhenotypeCreator(Auditor[typing.Tuple[str, bool], typing.Sequence[Phenotype]]):
    """
    `PhenotypeCreator` validates the input phenotype features and prepares them for the downstream analysis.

    The creator expects an iterable with tuples that contain a CURIE and status. The CURIE must correspond
    to a HPO term identifier and status must be a `bool`.

    The creator prunes CURIES with simple errors such as malformed CURIE or non-HPO terms and validates the rest
    with HPO toolkit's validator.

    The results are wrapped into :class:`AuditReport`.
    """

    def __init__(self, hpo: hpotk.MinimalOntology,
                 validator: hpotk.validate.ValidationRunner):
        self._logger = logging.getLogger(__name__)
        self._hpo = hpotk.util.validate_instance(hpo, hpotk.MinimalOntology, 'hpo')
        self._validator = hpotk.util.validate_instance(validator, hpotk.validate.ValidationRunner, 'validator')

    def process(self, inputs: typing.Iterable[typing.Tuple[str, bool]], notepad: Notepad) -> typing.Sequence[Phenotype]:
        """Creates a list of Phenotype objects from term IDs and checks if the term IDs satisfy the validation requirements.

        Args:
            inputs (Iterable[Tuple[str, bool]]): A list of Tuples, structured (HPO IDs, boolean- True if observed)
            notepad: Node
        Returns:
            A sequence of Phenotype objects
        """
        phenotypes = []

        for i, (curie, is_observed) in enumerate(inputs):
            # Check the CURIE is well-formed
            try:
                term_id = hpotk.TermId.from_curie(curie)
            except ValueError as ve:
                notepad.add_warning(f'#{i} {ve.args[0]}',
                                 'Ensure the term ID consists of a prefix (e.g. `HP`) '
                                 'and id (e.g. `0001250`) joined by colon `:` or underscore `_`')
                continue

            # Check the term is an HPO concept
            if term_id.prefix != 'HP':
                notepad.add_warning(f'#{i} {term_id} is not an HPO term',
                                 'Remove non-HPO concepts from the analysis input')
                continue

            # Term must be present in HPO
            term = self._hpo.get_term(term_id)
            if term is None:
                notepad.add_warning(f'#{i} {term_id} is not in HPO version `{self._hpo.version}`',
                                 'Correct the HPO term or use the latest HPO for the analysis')
                continue

            if term.identifier != term_id:
                # Input includes an obsolete term ID. We emit a warning and update the term ID behind the scenes,
                # since `term.identifier` always returns the primary term ID.
                notepad.add_warning(f'#{i} {term_id} is an obsolete identifier for {term.name}',
                                 f'Replace {term_id} with the primary term ID {term.identifier}')

            phenotypes.append(Phenotype.from_term(term, is_observed))

        # Check we have some phenotype terms to work with.
        if len(phenotypes) == 0:
            notepad.add_warning(
                    f'No phenotype terms were left after the validation',
                    'Revise the phenotype terms and try again')
        else:
            vr = self._validator.validate_all(phenotypes)
            for result in vr.results:
                level = self._translate_level(result.level)
                if level is None:
                    # Should not happen. Please let the developers know about this issue!
                    raise ValueError(f'Unknown result validation level {result.level}')

                notepad.add_issue(level, result.message)

        return phenotypes

    @staticmethod
    def _translate_level(lvl: ValidationLevel) -> typing.Optional[Level]:
        if lvl == ValidationLevel.WARNING:
            return Level.WARN
        elif lvl == ValidationLevel.ERROR:
            return Level.ERROR
        else:
            return None
