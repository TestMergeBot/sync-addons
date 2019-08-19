# -*- coding: utf-8 -*-
# Copyright 2018-2019 Ivan Yelizariev <https://it-projects.info/team/yelizariev>
# Copyright 2018 Rafis Bikbov <https://it-projects.info/team/bikbov>
# Copyright 2019 Yan Chirino <https://xoe.solutions/>
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl.html).
import collections
import uuid

# python3
# import urllib.parse as urlparse

# python2
import urlparse
import urllib

from odoo import models, fields, api
from ..controllers import pinguin


class Namespace(models.Model):

    _name = 'openapi.namespace'
    _description = 'Integration'

    active = fields.Boolean('Active', default=True)
    name = fields.Char(
        'Name',
        required=True,
        help="""Integration name, e.g. ebay, amazon, magento, etc.
        The name is used in api endpoint""")
    description = fields.Char('Description')
    log_ids = fields.One2many('openapi.log', 'namespace_id', string='Logs')
    log_request = fields.Selection([
        ('disabled', 'Disabled'),
        ('info', 'Short'),
        ('debug', 'Full'),
    ], 'Log Requests', default='disabled')

    log_response = fields.Selection([
        ('disabled', 'Disabled'),
        ('error', 'Errors only'),
        ('debug', 'Full'),
    ], 'Log Responses', default='error')

    last_log_date = fields.Datetime(
        related='log_ids.create_date',
        string='Latest usage'
    )

    access_ids = fields.One2many('openapi.access', 'namespace_id', string='Accesses', context={'active_test': False})
    user_ids = fields.Many2many('res.users', string='Allowed Users', default=lambda self: self.env.user)

    token = fields.Char('Identification token',
                        default=lambda self: str(uuid.uuid4()), readonly=True,
                        required=True, copy=False,
                        help='Token passed by a query string parameter to access the specification.')
    spec_url = fields.Char('Specification Link', compute='_compute_spec_url')

    _sql_constraints = [
        ('name_uniq',
         'unique (name)',
         'A namespace already exists with this name. Namespace\'s name must be unique!')
    ]

    @api.multi
    def name_get(self):
        return [(record.id, "/api/v1/%s%s" % (record.name,
                                              ' (%s)' % record.description
                                              if record.description else ''))
                for record in self]

    @api.model
    def _fix_name(self, vals):
        if 'name' in vals:
            # python3
            # vals['name'] = urlparse.quote_plus(vals['name'].lower())
            # python2
            vals['name'] = urllib.quote_plus(vals['name'].lower())
        return vals

    @api.model
    def create(self, vals):
        vals = self._fix_name(vals)
        return super(Namespace, self).create(vals)

    @api.multi
    def write(self, vals):
        vals = self._fix_name(vals)
        return super(Namespace, self).write(vals)

    @api.multi
    def get_OAS(self):
        current_host = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        parsed_current_host = urlparse.urlparse(current_host)

        report_parameters = [
            {
                "name": "report_external_id",
                "in": "path",
                "description": "Report xml id or report name",
                "required": True,
                "type": "string",
            },
            {
                "name": "docids",
                "in": "path",
                "description": "One identifier or several identifiers separated by commas",
                "required": True,
                "type": "string",
            },
        ]
        spec = collections.OrderedDict([
            ('swagger', '2.0'),
            ('info', {
                "title": self.name,
                "version": self.write_date
            }),
            ('host', parsed_current_host.netloc),
            ('basePath', "/api/v1/%s" % self.name),
            ('schemes', [
                parsed_current_host.scheme
            ]),
            ('consumes', [
                "multipart/form-data",
                "application/x-www-form-urlencoded",
            ]),
            ('produces', [
                "application/json"
            ]),
            ('paths', {
                '/report/pdf/{report_external_id}/{docids}': {
                    'get': {
                        "summary": "Get PDF report file for %s namespace" % self.name,
                        'description': 'Returns PDF report file for %s namespace' % self.name,
                        "operationId": "getPdfReportFileFor%sNamespace" % self.name.capitalize(),
                        "produces": [
                            "application/pdf"
                        ],
                        "responses": {
                            "200": {
                                "description": "A PDF report file for %s namespace." % self.name,
                                "schema": {
                                    "type": "file"
                                }
                            }
                        },
                        "parameters": report_parameters,
                        "tags": ["report"]
                    }
                },
                '/report/html/{report_external_id}/{docids}': {
                    'get': {
                        "summary": "Get HTML report file for %s namespace" % self.name,
                        'description': 'Returns HTML report file for %s namespace' % self.name,
                        "operationId": "getHtmlReportFileFor%sNamespace" % self.name.capitalize(),
                        "produces": [
                            "application/pdf"
                        ],
                        "responses": {
                            "200": {
                                "description": "A HTML report file for %s namespace." % self.name,
                                "schema": {
                                    "type": "file"
                                }
                            }
                        },
                        "parameters": report_parameters,
                        "tags": ["report"]
                    }
                },
            }),
            ('definitions', {
                "ErrorResponse": {
                    "type": "object",
                    "required": [
                        "error",
                        "error_descrip"
                    ],
                    "properties": {
                        "error": {
                            "type": "string"
                        },
                        "error_descrip": {
                            "type": "string"
                        }
                    }
                },
            }),
            ('responses', {
                "400": {
                    "description": "Invalid Data",
                    "schema": {
                        "$ref": "#/definitions/ErrorResponse"
                    }
                },
                "401": {
                    "description": "Authentication information is missing or invalid",
                    "schema": {
                        "$ref": "#/definitions/ErrorResponse"
                    }
                },
                "500": {
                    "description": "Server Error",
                    "schema": {
                        "$ref": "#/definitions/ErrorResponse"
                    }
                }
            }),
            ('securityDefinitions', {
                'basicAuth': {
                    'type': 'basic'
                }
            }),
            ('security', [
                {'basicAuth': []}
            ]),
            ('tags', [])
        ])

        for openapi_access in self.access_ids.filtered('active'):
            OAS_part_for_model = openapi_access.get_OAS_part()
            spec['tags'].append(OAS_part_for_model['tag'])
            del OAS_part_for_model['tag']
            pinguin.update(spec, OAS_part_for_model)

        return spec

    @api.depends('name', 'token')
    def _compute_spec_url(self):
        for record in self:
            record.spec_url = "/api/v1/%s/swagger.json?token=%s&db=%s" % (record.name, record.token, self._cr.dbname)

    def reset_token(self):
        for record in self:
            token = str(uuid.uuid4())
            while self.search([('token', '=', token)]).exists():
                token = str(uuid.uuid4())
            record.write({'token': token})
