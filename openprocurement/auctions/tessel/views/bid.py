# -*- coding: utf-8 -*-
from openprocurement.auctions.core.utils import (
    apply_patch,
    context_unpack,
    get_now,
    json_view,
    opresource,
    save_auction,
    set_ownership,
)
from openprocurement.auctions.core.validation import validate_bid_data, validate_patch_bid_data
from openprocurement.auctions.core.views.mixins import AuctionBidResource

from openprocurement.auctions.tessel.constants import TENDER_PERIOD_STATUSES


@opresource(name='tessel:Auction Bids',
            collection_path='/auctions/{auction_id}/bids',
            path='/auctions/{auction_id}/bids/{bid_id}',
            auctionsprocurementMethodType="tessel",
            description="Tessel auction bids")
class TesselAuctionBidResource(AuctionBidResource):

    @json_view(content_type="application/json", permission='create_bid', validators=(validate_bid_data,))
    def collection_post(self):
        """Registration of new bid proposal

        Creating new Bid proposal
        -------------------------

        Example request to create bid proposal:

        .. sourcecode:: http

            POST /auctions/4879d3f8ee2443169b5fbbc9f89fa607/bids HTTP/1.1
            Host: example.com
            Accept: application/json

            {
                "data": {
                    "tenderers": [
                        {
                            "id": {
                                "name": "Державне управління справами",
                                "scheme": "https://ns.openprocurement.org/ua/edrpou",
                                "uid": "00037256",
                                "uri": "http://www.dus.gov.ua/"
                            },
                            "address": {
                                "countryName": "Україна",
                                "postalCode": "01220",
                                "region": "м. Київ",
                                "locality": "м. Київ",
                                "streetAddress": "вул. Банкова, 11, корпус 1"
                            }
                        }
                    ],
                    "value": {
                        "amount": 489,
                        "currency": "UAH",
                        "valueAddedTaxIncluded": true
                    }
                }
            }

        This is what one should expect in response:

        .. sourcecode:: http

            HTTP/1.1 201 Created
            Content-Type: application/json

            {
                "data": {
                    "id": "4879d3f8ee2443169b5fbbc9f89fa607",
                    "status": "registration",
                    "date": "2014-10-28T11:44:17.947Z",
                    "tenderers": [
                        {
                            "id": {
                                "name": "Державне управління справами",
                                "scheme": "https://ns.openprocurement.org/ua/edrpou",
                                "uid": "00037256",
                                "uri": "http://www.dus.gov.ua/"
                            },
                            "address": {
                                "countryName": "Україна",
                                "postalCode": "01220",
                                "region": "м. Київ",
                                "locality": "м. Київ",
                                "streetAddress": "вул. Банкова, 11, корпус 1"
                            }
                        }
                    ],
                    "value": {
                        "amount": 489,
                        "currency": "UAH",
                        "valueAddedTaxIncluded": true
                    }
                }
            }

        """
        # See https://github.com/open-contracting/standard/issues/78#issuecomment-59830415
        # for more info upon schema
        auction = self.request.validated['auction']
        if self.request.validated['auction_status'] not in TENDER_PERIOD_STATUSES:
            self.request.errors.add('body', 'data', 'Can\'t add bid in current ({}) auction status'.format(self.request.validated['auction_status']))
            self.request.errors.status = 403
            return
        if auction.tenderPeriod.startDate and get_now() < auction.tenderPeriod.startDate or get_now() > auction.tenderPeriod.endDate:
            self.request.errors.add('body', 'data',
                                    'Bid can be added only during the tendering period: from ({}) to ({}).'.format(
                                        auction.tenderPeriod.startDate and auction.tenderPeriod.startDate.isoformat(),
                                        auction.tenderPeriod.endDate.isoformat()))
            self.request.errors.status = 403
            return
        bid = self.request.validated['bid']
        set_ownership(bid, self.request)
        auction.bids.append(bid)
        auction.modified = False
        if save_auction(self.request):
            self.LOGGER.info('Created auction bid {}'.format(bid.id),
                             extra=context_unpack(self.request, {'MESSAGE_ID': 'auction_bid_create'},
                                                  {'bid_id': bid.id}))
            self.request.response.status = 201
            route = self.request.matched_route.name.replace("collection_", "")
            self.request.response.headers['Location'] = self.request.current_route_url(_route_name=route, bid_id=bid.id,
                                                                                       _query={})
            return {
                'data': bid.serialize('view'),
                'access': {
                    'token': bid.owner_token
                }
            }

    @json_view(content_type="application/json", permission='edit_bid', validators=(validate_patch_bid_data,))
    def patch(self):
        """Update of proposal

        Example request to change bid proposal:

        .. sourcecode:: http

            PATCH /auctions/4879d3f8ee2443169b5fbbc9f89fa607/bids/71b6c23ed8944d688e92a31ec8c3f61a HTTP/1.1
            Host: example.com
            Accept: application/json

            {
                "data": {
                    "value": {
                        "amount": 600
                    }
                }
            }

        And here is the response to be expected:

        .. sourcecode:: http

            HTTP/1.0 200 OK
            Content-Type: application/json

            {
                "data": {
                    "value": {
                        "amount": 600,
                        "currency": "UAH",
                        "valueAddedTaxIncluded": true
                    }
                }
            }

        """

        if self.request.authenticated_role != 'Administrator' and self.request.validated['auction_status'] not in TENDER_PERIOD_STATUSES:
            self.request.errors.add('body', 'data', 'Can\'t update bid in current ({}) auction status'.format(self.request.validated['auction_status']))
            self.request.errors.status = 403
            return
        auction = self.request.validated['auction']
        if self.request.authenticated_role != 'Administrator' and (auction.tenderPeriod.startDate and get_now() < auction.tenderPeriod.startDate or get_now() > auction.tenderPeriod.endDate):
            self.request.errors.add('body', 'data', 'Bid can be updated only during the tendering period: from ({}) to ({}).'.format(auction.tenderPeriod.startDate and auction.tenderPeriod.startDate.isoformat(), auction.tenderPeriod.endDate.isoformat()))
            self.request.errors.status = 403
            return
        if self.request.authenticated_role != 'Administrator':
            bid_status_to = self.request.validated['data'].get("status")
            if bid_status_to != self.request.context.status and bid_status_to != "active":
                self.request.errors.add('body', 'bid', 'Can\'t update bid to ({}) status'.format(bid_status_to))
                self.request.errors.status = 403
                return
        self.request.validated['auction'].modified = False
        if apply_patch(self.request, src=self.request.context.serialize()):
            self.LOGGER.info('Updated auction bid {}'.format(self.request.context.id),
                        extra=context_unpack(self.request, {'MESSAGE_ID': 'auction_bid_patch'}))
            return {'data': self.request.context.serialize("view")}

    @json_view(permission='delete_bid')
    def delete(self):
        """Cancelling the proposal

        Example request for cancelling the proposal:

        .. sourcecode:: http

            DELETE /auctions/4879d3f8ee2443169b5fbbc9f89fa607/bids/71b6c23ed8944d688e92a31ec8c3f61a HTTP/1.1
            Host: example.com
            Accept: application/json

        And here is the response to be expected:

        .. sourcecode:: http

            HTTP/1.0 200 OK
            Content-Type: application/json

            {
                "data": {
                    "value": {
                        "amount": 489,
                        "currency": "UAH",
                        "valueAddedTaxIncluded": true
                    }
                }
            }

        """
        # Delete bid permission where deny for everyone
        # For return possibility delete bid remove this function
        bid = self.request.context
        if self.request.validated['auction_status'] != 'active.tendering':
            self.request.errors.add('body', 'data', 'Can\'t delete bid in current ({}) auction status'.format(self.request.validated['auction_status']))
            self.request.errors.status = 403
            return
        auction = self.request.validated['auction']
        if auction.tenderPeriod.startDate and get_now() < auction.tenderPeriod.startDate or get_now() > auction.tenderPeriod.endDate:
            self.request.errors.add('body', 'data', 'Bid can be deleted only during the tendering period: from ({}) to ({}).'.format(auction.tenderPeriod.startDate and auction.tenderPeriod.startDate.isoformat(), auction.tenderPeriod.endDate.isoformat()))
            self.request.errors.status = 403
            return
        res = bid.serialize("view")
        self.request.validated['auction'].bids.remove(bid)
        self.request.validated['auction'].modified = False
        if save_auction(self.request):
            self.LOGGER.info('Deleted auction bid {}'.format(self.request.context.id),
                        extra=context_unpack(self.request, {'MESSAGE_ID': 'auction_bid_delete'}))
            return {'data': res}

