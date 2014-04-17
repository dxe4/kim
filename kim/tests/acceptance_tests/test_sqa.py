#!/usr/bin/python
# -*- coding: utf-8 -*-

import unittest
from iso8601.iso8601 import Utc

from kim.serializers import Field
from kim.roles import Role
from kim import types
from kim.contrib.sqa import SQASerializer, NestedForeignKey
from kim.roles import whitelist, blacklist

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy import (
    Column,
    Integer,
    String,
    ForeignKey,
    DateTime
)

from datetime import datetime

from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class User(Base):

    __tablename__ = 'user'

    id = Column(Integer, primary_key=True)
    name = Column(Integer, nullable=False)
    signup_date = Column(DateTime, nullable=True)

    contact = Column(Integer, ForeignKey('contact_detail.id'), nullable=False)
    contact_details = relationship("ContactDetail", backref="users")


class ContactDetail(Base):

    __tablename__ = "contact_detail"

    id = Column(Integer, primary_key=True)
    phone = Column(String, nullable=False)
    email = Column(String, nullable=True)
    address_id = Column(Integer, ForeignKey('address.id'), nullable=False)

    address = relationship("Address", backref="contact")


class Address(Base):

    __tablename__ = 'address'

    id = Column(Integer, primary_key=True)
    address_1 = Column(String, nullable=True)
    address_2 = Column(String, nullable=True)
    postcode = Column(String, nullable=False)
    city = Column(String, nullable=True)
    country = Column(String, nullable=False)


class AddressSerializer(SQASerializer):
    __model__ = Address

    country = Field(types.String)
    postcode = Field(types.String)


class ContactSerializer(SQASerializer):
    __model__ = ContactDetail

    id = Field(types.Integer(read_only=True))
    phone = Field(types.String)
    address = Field(types.Nested(mapped=AddressSerializer,
                                 role=Role('foo', 'country', 'postcode')))


class UserSerializer(SQASerializer):
    __model__ = User

    id = Field(types.Integer(read_only=True))
    full_name = Field(types.String, source='name')
    contact = Field(types.Nested(mapped=ContactSerializer), source='contact_details')
    signup_date = Field(types.DateTime(required=False))
    contact_id = Field(NestedForeignKey(mapped=ContactSerializer), source='contact_details')

    class Meta:
        roles = {'full': blacklist('full', *['contact_id']),
                 'simple': whitelist('simple', *['id', 'full_name', 'contact_id'])}


class SQAAcceptanceTests(unittest.TestCase):

    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        Session = sessionmaker(bind=self.engine)
        self.session = Session()
        Base.metadata.create_all(self.engine)

        self.address = Address(address_1='2 easy street',
                               address_2='other',
                               postcode='sm00ln',
                               city='london',
                               country='UK')
        self.deets = ContactDetail(address=self.address,
                           phone='07967168590',
                           email='mike@mike.com')


        self.session.add(self.address)
        self.session.flush()

        self.session.add(self.deets)
        self.session.flush()

        self.user = User(name='foo', contact_details=self.deets,
                         signup_date=datetime(2014, 4, 11, 4, 6, 2))
        self.session.add(self.user)
        self.session.commit()


    def tearDown(self):

        Base.metadata.drop_all(self.engine)

    def test_nested_serialize(self):

        serializer = UserSerializer(instance=self.user)
        result = serializer.serialize(role='full')

        exp = {
            'id': self.user.id,
            'full_name': self.user.name,
            'contact': {
                'id': self.deets.id,
                'phone': self.deets.phone,
                'address': {
                    'country': self.address.country,
                    'postcode': self.address.postcode,
                }
            },
            'signup_date': '2014-04-11T04:06:02'
        }
        self.assertDictEqual(result, exp)

    def test_nested_marshal_new_object(self):

        data = {
            'full_name': 'bob',
            'contact': {
                'phone': '082345234',
                'address': {
                    'country': 'uk',
                    'postcode': 'sg1 3ab',
                }
            },
            'signup_date': '2014-06-12T19:06:02'
        }

        serializer = UserSerializer(input=data)
        result = serializer.marshal(role='full')

        self.assertTrue(isinstance(result, User))
        self.assertEqual(result.name, 'bob')
        self.assertEqual(result.signup_date, datetime(2014, 6, 12, 19, 6, 2, tzinfo=Utc()))

        contact_details = result.contact_details
        self.assertTrue(isinstance(contact_details, ContactDetail))
        self.assertEqual(contact_details.phone, '082345234')

        address = result.contact_details.address
        self.assertTrue(isinstance(address, Address))
        self.assertEqual(address.country, 'uk')
        self.assertEqual(address.postcode, 'sg1 3ab')

        self.assertIsNone(result.id)

        self.session.add(result)
        self.session.commit()

        self.assertIsNotNone(result.id)

    def test_nested_marshal_existing_object(self):

        data = {
            'full_name': 'bob',
            'contact': {
                'phone': '082345234',
                'address': {
                    'country': 'uk',
                    'postcode': 'sg1 3ab',
                }
            }
        }

        serializer = UserSerializer(input=data, instance=self.user)
        result = serializer.marshal(role='full')

        self.assertTrue(isinstance(result, User))
        self.assertEqual(result.name, 'bob')

        contact_details = result.contact_details
        self.assertTrue(isinstance(contact_details, ContactDetail))
        self.assertEqual(contact_details.phone, '082345234')
        self.assertEqual(contact_details.email, 'mike@mike.com')

        address = result.contact_details.address
        self.assertTrue(isinstance(address, Address))
        self.assertEqual(address.country, 'uk')
        self.assertEqual(address.postcode, 'sg1 3ab')
        self.assertEqual(address.city, 'london')

        self.session.add(result)
        self.session.commit()

    def test_foreignkey_field(self):
        data = {
            'full_name': 'bob',
            'contact_id': self.deets.id,
        }

        def contact_validator(id):
            return self.session.query(ContactDetail).get(id)
            # return True if self.session.query(ContactDetail).get(id) else False

        UserSerializer.base_fields['contact_id'].field_type.id_validator = contact_validator

        serializer = UserSerializer(input=data)
        result = serializer.marshal(role='simple')


        import ipdb; ipdb.set_trace()