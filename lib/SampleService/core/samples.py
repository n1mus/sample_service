'''
Core class for saving and getting samples.
'''

import datetime
import uuid as _uuid
from uuid import UUID

from typing import Optional, Callable, Tuple

from SampleService.core.arg_checkers import not_falsy as _not_falsy
from SampleService.core.acls import SampleAccessType as _SampleAccessType
from SampleService.core.acls import SampleACL
from SampleService.core.errors import UnauthorizedError as _UnauthorizedError
from SampleService.core.errors import IllegalParameterError as _IllegalParameterError
from SampleService.core.sample import Sample, SampleWithID
from SampleService.core.storage.arango_sample_storage import ArangoSampleStorage


class Samples:
    '''
    Class implementing sample manipulation operations.
    '''

    def __init__(
            self,
            storage: ArangoSampleStorage,
            now: Callable[[], datetime.datetime] = lambda: datetime.datetime.now(
                tz=datetime.timezone.utc),
            uuid_gen: Callable[[], UUID] = lambda: _uuid.uuid4()):
        '''
        Create the class.

        :param storage: the storage system to use.
        '''
        # don't publicize these params
        # :param now: A callable that returns the current time. Primarily used for testing.
        # :param uuid_gen: A callable that returns a random UUID. Primarily used for testing.
        # extract an interface from ASS if needed.
        self._storage = _not_falsy(storage, 'storage')
        self._now = _not_falsy(now, 'now')
        self._uuid_gen = _not_falsy(uuid_gen, 'uuid_gen')

    def save_sample(
            self,
            sample: Sample,
            user: str,
            id_: UUID = None,
            prior_version: Optional[int] = None) -> Tuple[UUID, int]:
        '''
        Save a sample.

        :param sample: the sample to save.
        :param user: the username of the user saving the sample.
        :param id_: if the sample is a new version of a sample, the ID of the sample which will
            get a new version.
        :prior_version: if id_ is included, specifying prior_version will ensure that the new
            sample is saved with version prior_version + 1 or not at all.
        :returns a tuple of the sample ID and version.
        :raises IllegalParameterError: if the prior version is < 1
        :raises UnauthorizedError: if the user does not have write permission to the sample when
            saving a new version.
        :raises NoSuchSampleError: if the sample does not exist when saving a new version.
        :raises SampleStorageError: if the sample could not be retrieved when saving a new version
            or if the sample fails to save.
        :raises ConcurrencyError: if the sample's version is not equal to prior_version.
        '''
        _not_falsy(sample, 'sample')
        _not_falsy(user, 'user')
        # TODO validate metadata
        if id_:
            if prior_version is not None and prior_version < 1:
                raise _IllegalParameterError('Prior version must be > 0')
            self._check_perms(id_, user, _SampleAccessType.WRITE)
            swid = SampleWithID(id_, list(sample.nodes), self._now(), sample.name)
            ver = self._storage.save_sample_version(swid, prior_version)
        else:
            id_ = self._uuid_gen()
            swid = SampleWithID(id_, list(sample.nodes), self._now(), sample.name)
            # don't bother checking output since we created uuid
            self._storage.save_sample(user, swid)
            ver = 1
        return (id_, ver)

    def _check_perms(self, id_: UUID, user: str, access: _SampleAccessType):
        acls = self._storage.get_sample_acls(id_)
        if self._get_access_level(acls, user) < access:
            errmsg = f'User {user} {self._unauth_errmap[access]} sample {id_}'
            raise _UnauthorizedError(errmsg)

    _unauth_errmap = {_SampleAccessType.OWNER: 'does not own',
                      _SampleAccessType.ADMIN: 'cannot adminstrate',
                      _SampleAccessType.WRITE: 'cannot write to',
                      _SampleAccessType.READ: 'cannot read'}

    def _get_access_level(self, acls: SampleACL, user: str):
        if user == acls.owner:
            return _SampleAccessType.OWNER
        if user in acls.admin:
            return _SampleAccessType.ADMIN
        if user in acls.write:
            return _SampleAccessType.WRITE
        if user in acls.read:
            return _SampleAccessType.READ
        return _SampleAccessType.NONE