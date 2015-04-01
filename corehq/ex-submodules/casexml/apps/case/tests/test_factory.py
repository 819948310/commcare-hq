import uuid
from django.test import SimpleTestCase, TestCase
from casexml.apps.case.mock import CaseStructure, CaseRelationship, CaseFactory
from casexml.apps.case.models import CommCareCase


class CaseRelationshipTest(SimpleTestCase):

    def test_defaults(self):
        relationship = CaseRelationship(CaseStructure())
        self.assertEqual(relationship.relationship, relationship.DEFAULT_RELATIONSHIP)
        self.assertEqual(relationship.related_type, relationship.DEFAULT_RELATED_CASE_TYPE)


class CaseStructureTest(SimpleTestCase):

    def test_index(self):
        parent_case_id = uuid.uuid4().hex
        structure = CaseStructure(
            relationships=[
                CaseRelationship(CaseStructure(case_id=parent_case_id))
            ]
        )
        self.assertEqual(
            {CaseRelationship.DEFAULT_RELATIONSHIP: (CaseRelationship.DEFAULT_RELATED_CASE_TYPE, parent_case_id)},
            structure.index,
        )

    def test_multiple_indices(self):
        indices = [
            ('mother_case_id', 'mother', 'mother_type'),
            ('father_case_id', 'father', 'father_type'),
        ]
        structure = CaseStructure(
            relationships=[
                CaseRelationship(CaseStructure(case_id=i[0]), relationship=i[1], related_type=i[2])
                for i in indices
            ]
        )
        self.assertEqual(
            {i[1]: (i[2], i[0]) for i in indices},
            structure.index
        )

    def test_walk_ids(self):
        case_id = uuid.uuid4().hex
        parent_case_id = uuid.uuid4().hex
        grandparent_case_id = uuid.uuid4().hex
        structure = CaseStructure(
            case_id=case_id,
            relationships=[
                CaseRelationship(CaseStructure(
                    case_id=parent_case_id,
                    relationships=[
                        CaseRelationship(CaseStructure(case_id=grandparent_case_id))
                    ]))
            ]
        )
        self.assertEqual(
            [case_id, parent_case_id, grandparent_case_id],
            list(structure.walk_ids())
        )


class CaseFactoryTest(TestCase):

    def test_simple_create(self):
        factory = CaseFactory()
        case = factory.create_case()
        self.assertTrue(CommCareCase.get_db().doc_exist(case._id))

    def test_create_overrides(self):
        factory = CaseFactory()
        case = factory.create_case(owner_id='somebody', update={'custom_prop': 'custom_value'})
        self.assertEqual('somebody', case.owner_id)
        self.assertEqual('custom_value', case.custom_prop)

    def test_domain(self):
        domain = uuid.uuid4().hex
        factory = CaseFactory(domain=domain)
        case = factory.create_case()
        self.assertEqual(domain, case.domain)

    def test_factory_defaults(self):
        owner_id = uuid.uuid4().hex
        factory = CaseFactory(case_defaults={'owner_id': owner_id})
        case = factory.create_case()
        self.assertEqual(owner_id, case.owner_id)

    def test_create_from_structure(self):
        owner_id = uuid.uuid4().hex
        factory = CaseFactory(case_defaults={
            'owner_id': owner_id,
            'create': True,
            'update': {'custom_prop': 'custom_value'}
        })
        case_id = uuid.uuid4().hex
        child_case_id = uuid.uuid4().hex
        parent_case_id = uuid.uuid4().hex
        structures = [
            CaseStructure(case_id=case_id),
            CaseStructure(
                case_id=child_case_id,
                relationships=[
                    CaseRelationship(CaseStructure(case_id=parent_case_id))
                ]
            )
        ]
        cases = factory.create_or_update_cases(structures)
        for case in cases:
            self.assertEqual(owner_id, case.owner_id)
            self.assertEqual('custom_value', case.custom_prop)

        [regular, child, parent] = cases
        self.assertEqual(1, len(child.indices))
        self.assertEqual(parent_case_id, child.indices[0].referenced_id)
        self.assertEqual(2, len(regular.actions))  # create + update
        self.assertEqual(2, len(parent.actions))  # create + update
        self.assertEqual(3, len(child.actions))  # create + update + index
