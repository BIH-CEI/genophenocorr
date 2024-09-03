from itertools import count
import typing

import hpotk
import numpy as np
import pandas as pd
import pytest

from gpsea.analysis.mtc_filter import HpoMtcFilter, SpecifiedTermsMtcFilter
from gpsea.analysis.predicate import PatientCategories
from gpsea.analysis.predicate.genotype import GenotypePolyPredicate
from gpsea.analysis.predicate.phenotype import PhenotypePolyPredicate
from gpsea.analysis.pcats import apply_predicates_on_patients
from gpsea.model import Cohort


class TestHpoMtcFilter:

    @pytest.fixture
    def mtc_filter(
        self,
        hpo: hpotk.MinimalOntology,
    ) -> HpoMtcFilter:
        return HpoMtcFilter.default_filter(
            hpo=hpo,
            term_frequency_threshold=0.2,
        )

    @pytest.fixture(scope='class')
    def patient_counts(
            self,
            suox_cohort: Cohort,
            suox_gt_predicate: GenotypePolyPredicate,
            suox_pheno_predicates: typing.Sequence[PhenotypePolyPredicate[hpotk.TermId]],
    ) -> typing.Sequence[pd.DataFrame]:
        _, counts = apply_predicates_on_patients(
            patients=suox_cohort.all_patients,
            gt_predicate=suox_gt_predicate,
            pheno_predicates=suox_pheno_predicates,
        )
        return counts

    @pytest.fixture(scope='class')
    def gt_categories(self) -> pd.Index:
        return pd.Index([PatientCategories.YES, PatientCategories.NO])

    @pytest.fixture(scope='class')
    def pheno_categories(self) -> pd.Index:
        return pd.Index([PatientCategories.YES, PatientCategories.NO])

    @staticmethod
    def prepare_counts_df(
        counts,
        index: pd.Index,
        columns: pd.Index,
    ):
        values = np.array(counts).reshape((2, 2))
        return pd.DataFrame(data=values, index=index, columns=columns)

    @pytest.mark.parametrize(
        "counts, expected",
        [
            ((10, 1, 15, 0), False),
            ((10, 0, 15, 1), False),
            ((10, 0, 15, 0), True),
            ((0, 15, 0, 19), True),
        ]
    )
    def test_one_genotype_has_zero_hpo_observations(
            self,
            counts: typing.Tuple[int],
            expected: bool,
            gt_categories: pd.Index,
            pheno_categories: pd.Index,
    ):
        counts_df = TestHpoMtcFilter.prepare_counts_df(counts, gt_categories, pheno_categories)

        actual = HpoMtcFilter.one_genotype_has_zero_hpo_observations(
            counts=counts_df,
            gt_categories=gt_categories,
        )

        assert actual == expected

    @pytest.mark.parametrize(
        "counts, expected",
        [
            ((1, 0, 20, 30), False),
            ((2, 0, 20, 30), True),

            ((0, 1, 20, 30), False),
            ((0, 2, 20, 30), True),

            ((0, 0, 20, 30), False),
            ((2, 2, 20, 30), True),
        ]
    )
    def test_some_cell_has_greater_than_one_count(
            self,
            counts: typing.Tuple[int],
            expected: bool,
            gt_categories: pd.Index,
            pheno_categories: pd.Index,
    ):
        counts_df = TestHpoMtcFilter.prepare_counts_df(counts, gt_categories, pheno_categories)

        actual = HpoMtcFilter.some_cell_has_greater_than_one_count(counts=counts_df)

        assert actual == expected

    @pytest.mark.parametrize(
        "counts, expected",
        [
            ((10, 100, 50, 500), True),
            ((95, 60, 144 - 95, 71 - 60), False),
            ((40, 15, 18, 15), False),
        ]
    )
    def test_genotypes_have_same_hpo_proportions(
            self,
            counts: typing.Tuple[int],
            expected: bool,
            gt_categories: pd.Index,
            pheno_categories: pd.Index,
    ):
        counts_df = TestHpoMtcFilter.prepare_counts_df(counts, gt_categories, pheno_categories)

        actual = HpoMtcFilter.genotypes_have_same_hpo_proportions(
            counts=counts_df,
            gt_categories=gt_categories,
        )

        assert actual == expected

    def test_filter_terms_to_test(
        self,
        mtc_filter: HpoMtcFilter,
        suox_gt_predicate: GenotypePolyPredicate,
        suox_pheno_predicates: typing.Sequence[PhenotypePolyPredicate[hpotk.TermId]],
        patient_counts: typing.Sequence[pd.DataFrame],
    ):
        phenotypes = [p.phenotype for p in suox_pheno_predicates]
        
        mtc_report = mtc_filter.filter(
            gt_predicate=suox_gt_predicate,
            phenotypes=phenotypes,
            counts=patient_counts,
        )

        assert isinstance(mtc_report, typing.Sequence)
        assert len(mtc_report) == 5

        is_ok = [r.is_passed() for r in mtc_report]
        assert is_ok == [True, True, False, True, True]

        reasons = [r.reason for r in mtc_report]
        assert reasons == [
            None, None,
            'Skipping term because all genotypes have same HPO observed proportions',
            None, None,
        ]

    def test_specified_term_mtc_filter(
        self,
        suox_gt_predicate: GenotypePolyPredicate,
        suox_pheno_predicates: typing.Sequence[PhenotypePolyPredicate[hpotk.TermId]],
        patient_counts: typing.Sequence[pd.DataFrame],
    ):
        """
        The point of this test is to check that if we filter to test only one term ("HP:0032350"), then this
        is the only term that should survive the filter. We start with a total of five terms (n_usable==5),
        but after our filter, only one survives, and we have four cases in which the
        reason for filtering out is 'Non-specified term'
        """
        specified_filter = SpecifiedTermsMtcFilter(
            terms_to_test=(hpotk.TermId.from_curie("HP:0032350"),),
        )
        phenotypes = [p.phenotype for p in suox_pheno_predicates]
        
        mtc_report = specified_filter.filter(
            gt_predicate=suox_gt_predicate,
            phenotypes=phenotypes,
            counts=patient_counts,
        )
        assert isinstance(mtc_report, typing.Sequence)
        assert len(mtc_report) == 5

        is_passed = [r.is_passed() for r in mtc_report]
        assert is_passed == [
            False, False, True, False, False,
        ]

        reasons = [r.reason for r in mtc_report]
        assert reasons == [
            'Non-specified term',
            'Non-specified term',
            None,
            'Non-specified term',
            'Non-specified term',
        ]

    def test_min_observed_HPO_threshold(
        self,
        suox_pheno_predicates: typing.Sequence[PhenotypePolyPredicate[hpotk.TermId]],
        patient_counts: typing.Sequence[pd.DataFrame],
    ):
        """
        In our heuristic filter, we only test terms that have at least a threshold
        frequency in at least one of the groups. We use the `patient_counts` - a sequence of DataFrames
        with 2x2 contingenicy tables of counts. For instance, each column will have one row for
        PatientCategories.YES and one for PatientCategories.NO, indicating counts of measured observed/excluded
        HPO phenotypes. Each column is a certain genotype, e.g., MISSENSE or NON-MISSENSE. We want the
        function to return the maximum frequency. In each column, the frequency is calculate by
        PatientCategories.YES / (PatientCategories.YES+PatientCategories.NO). This function tests that this works
        for all of the HPO terms in the dictionary.
        """
        EPSILON = 0.001
        curie2idx = {
            p.phenotype.value: i
            for i, p
            in enumerate(suox_pheno_predicates)
        }
        # Ectopia lentis HP:0001083  (6 9  1 2), freqs are 6/15=0.4 and 1/3=0.33
        ectopia = patient_counts[curie2idx["HP:0001083"]]
        max_f = HpoMtcFilter.get_maximum_group_observed_HPO_frequency(ectopia)
        assert max_f == pytest.approx(0.4, abs=EPSILON)
        
        # Seizure HP:0001250 (17 7 11 0), freqs are 17/24=0.7083 and 11/11=1
        seizure = patient_counts[curie2idx["HP:0001250"]]
        max_f = HpoMtcFilter.get_maximum_group_observed_HPO_frequency(seizure)
        assert max_f == pytest.approx(1.0, abs=EPSILON)
        
        # Sulfocysteinuria HP:0032350 (11 0 2 0), freqs are both 1
        sulfocysteinuria = patient_counts[curie2idx["HP:0032350"]]
        max_f = HpoMtcFilter.get_maximum_group_observed_HPO_frequency(sulfocysteinuria)
        assert max_f == pytest.approx(1.0, abs=EPSILON)
        
        # Neurodevelopmental delay HP:0012758 (4 13 4 4), freqs are 4/17 = 0.235 and 4/8=0.5
        ndelay = patient_counts[curie2idx["HP:0012758"]]
        max_f = HpoMtcFilter.get_maximum_group_observed_HPO_frequency(ndelay)
        assert max_f == pytest.approx(0.5, abs=EPSILON)
        
        # Hypertonia HP:0001276 (7 9 4 3) fresa are 7/16=0.4375 and 4/7=0.5714
        hypertonia = patient_counts[curie2idx["HP:0001276"]]
        max_f = HpoMtcFilter.get_maximum_group_observed_HPO_frequency(hypertonia)
        assert max_f == pytest.approx(0.5714, abs=EPSILON)
