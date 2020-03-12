#! -*- encoding: utf-8
import os, time, datetime, re
import logging
import csv
from collections import namedtuple

from lxml import etree
from svgpathparse import parsePath

logging.basicConfig(format='%(asctime)s %(levelname)-5.5s %(message)s')

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

def pascal_row(n):
    # This returns the nth row of Pascal's Triangle
    result = [1]
    x, numerator = 1, n
    for denominator in range(1, n//2+1):
        # print(numerator,denominator,x)
        x *= numerator
        x /= denominator
        result.append(x)
        numerator -= 1
    if n&1 == 0:
        # n is even
        result.extend(reversed(result[:-1]))
    else:
        result.extend(reversed(result))
    return result

def make_bezier(xys):
    # xys should be a sequence of 2-tuples (Bezier control points)
    n = len(xys)
    combinations = pascal_row(n-1)
    def bezier(ts):
        # This uses the generalized formula for bezier curves
        # http://en.wikipedia.org/wiki/B%C3%A9zier_curve#Generalization
        result = []
        for t in ts:
            tpowers = (t**i for i in range(n))
            upowers = reversed([(1-t)**i for i in range(n)])
            coefs = [c*a*b for c, a, b in zip(combinations, tpowers, upowers)]
            result.append(
                tuple(sum([coef*p for coef, p in zip(coefs, ps)]) for ps in zip(*xys)))
        return result
    return bezier

class LayerId(object):
    id_re = re.compile(r'(\d+)[a-z]? +([a-z]+)/([a-z]+).*?', re.I)
    id2_re = re.compile(r'(?:Section)+\ *(\d+)', re.I)
    id3_re = re.compile(r'(?:Sezione)+\ *(\d+)cau', re.I)
    def __init__(self, layer_id):
        self.log = logging.getLogger(__name__)
        self.layer_id = layer_id
        matches = self.id_re.match(layer_id)
        if matches:
            self.seq = matches.group(1)
            self.lr = matches.group(2)
            self.rc = matches.group(3)
            self.log.info('first matched: seq %s lr %s rc %s', self.seq, self.lr, self.rc)
        else:
            matches = self.id2_re.match(layer_id)
            if matches:
                self.seq = matches.group(1)
                self.lr = None
                self.rc = 'r'
                self.log.info('second matched: seq %s lr %s rc %s', self.seq, self.lr, self.rc)
            else:
                matches = self.id3_re.match(layer_id)
                if matches:
                    self.seq = matches.group(1)
                    self.lr = None
                    self.rc = 'c'
                else:
                    self.seq = -1
                    self.lr = None
                    self.rc = None


    def __lt__(self, other):
        if self.rc == 'r' and other.rc == 'c':
            return True
        elif self.rc == 'c' and other.rc == 'r':
            return False
        elif self.rc == other.rc and self.rc == 'r':
            return self.seq < other.seq
        elif self.rc == other.rc and self.rc == 'c':
            return self.seq >= other.seq
        else:
            try:
                return int(self.layer_id) < int(other.layer_id)
            except ValueError:
                return self.layer_id < other.layer_id

class Caret(object):
    ts = [t/5. for t in range(6)]

    def __init__(self, caret_name, spacing=6.):
        self.caret_name = caret_name
        self._all_vertices = []
        self._cells = []
        self._contours = []
        self._layers = {}
        self._spacing = spacing

    def get_vertices(self, parsed_d):
        vertices = []
        for cmd, _vertices in parsed_d:
            if cmd == 'Z':
                vertices.append(vertices[0])
            elif cmd == 'M' or cmd == 'L':
                vertices.append(tuple(_vertices))
            elif cmd == 'C':
                x0, y0, x1, y1, x2, y2 = _vertices
                bezier = make_bezier([(x0, y0), (x1, y1), (x2, y2)])
                vertices.extend(bezier(self.ts))
            else:
                raise ValueError('not support path cmd in svg')
        return vertices

    def parse_path(self, layer_id, path):
        #print etree.tostring(path)
        p = parsePath(path.get('d'))
        stroke = path.get('stroke')
        fill = path.get('fill')
        #color = stroke or fill
        #print color, p
        parsed_vertices = self.get_vertices(p)

        if stroke is not None:
            stroke = stroke.lower()
        if fill is not None:
            fill = fill.lower()

        # this is one cell
        if stroke == '#313185' or fill == '#313185' or fill == '#00aeef' or \
           stroke == '#0000ff' or fill == '#0000ff':
            self.add_cell(layer_id, 'mdplot.blue', parsed_vertices)

        elif stroke == '#ed1c24' or fill == '#ed1c24' or stroke == '#d52e2b' or fill == '#d52e2b':
            self.add_cell(layer_id, 'mdplot.red', parsed_vertices)

        elif stroke == '#fff200' or fill == '#fff200' or stroke == '#808000' or fill == '#808000':
            self.add_cell(layer_id, 'mdplot.yellow', parsed_vertices)

        else:
            if stroke != '#000000':
                log.warn('path stroke %s, fill %s treated as contour, vertices: %s', stroke, fill, len(parsed_vertices))
            self.add_contour(layer_id, parsed_vertices)

    def parse_polygon(self, layer_id, polygon):
        p = parsePath('M' + polygon.get('points'))
        stroke = polygon.get('stroke')
        fill = polygon.get('fill')
        #color = stroke or fill
        #print color, p
        parsed_vertices = self.get_vertices(p)

        if stroke is not None:
            stroke = stroke.lower()
        if fill is not None:
            fill = fill.lower()

        # this is one cell
        if stroke == '#313185' or fill == '#313185' or fill == '#00aeef' or \
           stroke == '#0000ff' or fill == '#0000ff':
            self.add_cell(layer_id, 'mdplot.blue', parsed_vertices)

        elif stroke == '#ed1c24' or fill == '#ed1c24' or stroke == '#d52e2b' or \
            fill == '#d52e2b' or fill == '#ff0000':
            self.add_cell(layer_id, 'mdplot.red', parsed_vertices)

        elif stroke == '#fff200' or fill == '#fff200' or stroke == '#808000' or fill == '#808000':
            self.add_cell(layer_id, 'mdplot.yellow', parsed_vertices)

        else:
            if stroke != '#000000':
                log.warn('polygon stroke %s fill %s treated as contour, vertices %s', stroke, fill, len(parsed_vertices))
            self.add_contour(layer_id, parsed_vertices)

    def parse_polyline(self, layer_id, polyline):
        p = parsePath('M' + polyline.get('points'))
        stroke = polyline.get('stroke')
        fill = polyline.get('fill')
        #color = stroke or fill
        #print color, p
        parsed_vertices = self.get_vertices(p)

        if stroke is not None:
            stroke = stroke.lower()
        if fill is not None:
            fill = fill.lower()

        # this is one cell
        if stroke == '#313185' or fill == '#313185' or fill == '#00aeef' or \
           stroke == '#0000ff' or fill == '#0000ff' or stroke == '#3a53a4':
            self.add_cell(layer_id, 'mdplot.blue', parsed_vertices)
        elif stroke == '#ed1c24' or fill == '#ed1c24' or stroke == '#d52e2b' or \
            fill == '#d52e2b' or fill == '#ff0000':
            self.add_cell(layer_id, 'mdplot.red', parsed_vertices)

        elif stroke == '#fff200' or fill == '#fff200' or stroke == '#808000' or fill == '#808000':
            self.add_cell(layer_id, 'mdplot.yellow', parsed_vertices)
        elif stroke == '#00884b' and len(parsed_vertices) > 5:
            self.add_contour(layer_id, parsed_vertices)
        else:
            if stroke != '#000000':
                log.warn('polyline stroke %s fill %s treated as contour, vertices %s', stroke, fill, len(parsed_vertices))
            self.add_contour(layer_id, parsed_vertices)

    def add_cell(self, layer_id, type_, vertices):
        log.debug('add cell type %s to layer %s', type_, layer_id)
        x_coords, y_coords = zip(*vertices)
        center = (sum(x_coords) / len(x_coords), sum(y_coords) / len(y_coords))
        layer = self._layers.get(layer_id, {})
        self._layers.setdefault(layer_id, layer)

        cells = layer.get('cells', [])
        layer.setdefault('cells', cells)

        cells.append([type_, center])
        self._all_vertices.append([center[0], center[1]])

    def add_contour(self, layer_id, vertices):
        log.debug('add contour vertices %s to layer %s', vertices, layer_id)
        layer = self._layers.get(layer_id, {})
        self._layers.setdefault(layer_id, layer)

        contours = layer.get('contours', [])
        layer.setdefault('contours', contours)

        contours.append(vertices)
        self._all_vertices.extend(vertices)

    def get_offsets(self):
        #x_series = [v[0] for v in self._all_vertices]
        #y_series = [v[1] for v in self._all_vertices]
        x_series, y_series = zip(*self._all_vertices)
        if all([len(x_series), len(y_series)]):
            offset_x = (min(x_series) + max(x_series)) / 2
            offset_y = (min(y_series) + max(y_series)) / 2
        else:
            offset_x = 0
            offset_y = 0
        return offset_x, offset_y

    def dump_cells(self):
        offset_x, offset_y = self.get_offsets()
        cells = []
        cells.extend([
            ['CSVF-FILE', '0'],
            ['csvf-section-start', 'header', '2'],
            ['tag', 'value'],
            ['Caret-Version', '5.65'],
            ['Date', '2012-02-06T15:25:58'],
            ['comment'],
            ['encoding', 'COMMA_SEPARATED_VALUE_FILE'],
            ['pubmed_id'],
            ['csvf-section-end', 'header'],
            ['csvf-section-start', 'Cells', '27'],
            ['Cell Number', 'X', 'Y', 'Z', 'Section', 'Name', 'Study Number', 'Geography', 'Area', 'Size', 'Statistic',
             'Comment', 'Structure', 'Class Name', 'SuMS ID Number', 'SuMS Repeat Number', 'SuMS Parent Cell Base ID',
             'SuMS Version Number', 'SuMS MSLID', 'Attribute ID', 'Study PubMed ID', 'Study Table Number',
             'Study Table Subheader', 'Study Figure Number', 'Study Figure Panel', 'Study Page Reference Number',
             'Study Page Reference Subheader'],
        ])
        idx = 0
        for layer_idx, layer_id in enumerate(sorted(self._layers.keys(), key=LayerId)):
            layer = self._layers[layer_id]
            log.info('dumping cells for layer index: %s, id: %s cells: %s', layer_idx, layer_id, len(layer.get('cells', [])))
            for type_, vertices in layer.get('cells', []):
                depth = layer_idx
                cells.append([
                    idx, vertices[0] - offset_x, offset_y - vertices[1], int(depth * self._spacing), depth, type_, '', '', '', '', '', '', '', 'mdplot'
            ])
                idx += 1
        cells.append(['csvf-section-end', 'Cells'])
        #fields = ['Cell_Number', 'X', 'Y', 'Z', 'Section', 'Name', 'Study_Number', 'Geography', 'Area', 'Size', 'Statistic',
        #     'Comment', 'Structure', 'Class_Name', 'SuMS_ID_Number', 'SuMS_Repeat_Number', 'SuMS_Parent_Cell_Base_ID',
        #     'SuMS_Version_Number', 'SuMS_MSLID', 'Attribute_ID', 'Study_PubMed_ID', 'Study_Table_Number',
        #     'Study_Table_Subheader', 'Study_Figure_Number', 'Study_Figure_Panel', 'Study_Page_Reference_Number',
        #     'Study_Page_Reference_Subheader']
        #MonashCell = namedtuple('MonashCell', fields)

        with open(os.path.join('caret', self.caret_name + '.contour_cells'), 'wb') as fout:
            writer = csv.writer(fout)
            writer.writerows(map(lambda l: l + ([''] * (27 - len(l))), cells))

    def dump_contours(self):
        offset_x, offset_y = self.get_offsets()
        contours_data = []
        contours_data.extend([
            'BeginHeader',
            'Caret-Version 5.61',
            'date mer feb 3 18:29:18 2010',
            'encoding ASCII',
            'pubmed_id',
            'EndHeader',
            'tag-version 1',
            'tag-number-of-contours %s' % 0,
            'tag-section-spacing %s' % (self._spacing),
            'tag-BEGIN-DATA'
        ])
        cnt = 0
        for layer_idx, layer_id in enumerate(sorted(self._layers.keys(), key=LayerId)):
            layer = self._layers[layer_id]
            log.info('dumping contours for layer index: %s id: %s cells: %s', layer_idx, layer_id, len(layer.get('cells', [])))
            for vertices in layer.get('contours', []):
                depth = layer_idx
                contours_data.append('%s %s %s' % (cnt, len(vertices), depth))
                for p in vertices:
                    contours_data.append('%s %s' % (p[0] - offset_x, offset_y - p[1]))
                cnt += 1

        contours_data[7] = 'tag-number-of-contours %s' % cnt

        with open(os.path.join('caret', self.caret_name + '.contours'), 'wb') as fout:
            fout.write('\n'.join(contours_data))
            fout.write('\n')

    def dump_cell_color(self):
        fieldnames = ['Name', 'Red', 'Green', 'Blue', 'Alpha', 'Point-Size', 'Line-Size', 'Symbol', 'SuMSColorID']
        #CellColor = namedtuple('CellColor', ['Name', 'Red', 'Green', 'Blue', 'Alpha', 'PointSize', 'LineSize', 'Symbol', 'SuMSColorID'])
        cc = []
        cc.extend([
            ['CSVF-FILE', '0', '', '', '', '', '', '', ''],
            ['csvf-section-start', 'header', '2', '', '', '', '', '', ''],
            ['tag', 'value', '0', '', '', '', '', '', ''],
            ['Caret-Version', '5.616', '', '', '', '', '', '', ''],
            ['Date', '2011-02-16T15:57:38', '', '', '', '', '', '', ''],
            ['comment', '', '', '', '', '', '', '', ''],
            ['encoding', 'COMMA_SEPARATED_VALUE_FILE', '', '', '', '', '', '', ''],
            ['pubmed_id', 'COMMA_SEPARATED_VALUE_FILE', '', '', '', '', '', '', ''],
            ['csvf-section-end', 'header', '', '', '', '', '', '', ''],
            ['csvf-section-start', 'Colors', '9', '', '', '', '', '', ''],
            fieldnames
        ])
        cc.append(['mdplot.red', '255', '0', '0', '255', '3.0', '1.0', 'POINT', ''])
        cc.append(['mdplot.green', '0', '255', '0', '255', '3.0', '1.0', 'POINT', ''])
        cc.append(['mdplot.blue', '0', '0', '255', '255', '3.0', '1.0', 'POINT', ''])
        cc.append(['mdplot.yellow', '255', '255', '0', '255', '3.0', '1.0', 'POINT', ''])
        cc.append(['csvf-section-end', 'Colors', '', '', '', '', '', '', ''])
        with open(os.path.join('caret', self.caret_name + '.contour_cell_color'), 'wb') as fout:
            writer = csv.writer(fout)
            writer.writerows(cc)

class Main(object):
    def __init__(self, spacing=6.):
        "initialize"
        self.ts = [t/5. for t in range(6)]
        self._spacing = spacing

    def get_vertices(self, parsed_d):
        vertices = []
        for cmd, _vertices in parsed_d:
            if cmd == 'Z':
                vertices.append(vertices[0])
            elif cmd == 'M' or cmd == 'L':
                vertices.append(tuple(_vertices))
            elif cmd == 'C':
                x0, y0, x1, y1, x2, y2 = _vertices
                bezier = make_bezier([(x0, y0), (x1, y1), (x2, y2)])
                vertices.extend(bezier(self.ts))
            else:
                raise ValueError('not support path cmd in svg')
        return vertices

    def run(self, fn_base):
        with open(fn_base + '.svg', 'rb') as f:
            p = etree.XMLParser(huge_tree=True)
            root = etree.parse(f, parser=p).getroot()

        nsmap = root.nsmap
        nsmap['svg'] = nsmap[None]
        del nsmap[None]
        nsmap['inkscape'] = 'http://www.inkscape.org/namespaces/inkscape'

        svg_ns = nsmap['svg']
        tags = {
            'groupmode': '{' + nsmap['inkscape'] + '}groupmode',
            'label': '{' + nsmap['inkscape'] + '}label',
        }
        #for x in root.xpath('.//svg:svg', namespaces=nsmap):
        caret = Caret(fn_base, self._spacing)

        for g in root.xpath('./svg:g', namespaces=nsmap):
            id_ = re.sub(r'_x([\da-fA-F][\da-fA-F])_', lambda match_o: chr(int(match_o.group(1), 16)), g.get('id'))
            id_ = id_.replace('_', ' ')
            layer_id = id_
            matches = re.search(r'(?:(\d+)([a-z]?))\s*.*$', layer_id)
            if matches:
                #log.info('working on layer %r %s', layer_id, matches.groups())
                slide = matches.group(1)
                section_suffix = matches.group(2)
                depth = slide
                for path in g.xpath('.//svg:path', namespaces=nsmap):
                    log.debug('parse path %s', etree.tostring(path))
                    caret.parse_path(layer_id, path)

                for polygon in g.xpath('.//svg:polygon', namespaces=nsmap):
                    caret.parse_polygon(layer_id, polygon)

                for polyline in g.xpath('.//svg:polyline', namespaces=nsmap):
                    caret.parse_polyline(layer_id, polyline)
            else:
                if id_ == 'Background':
                    continue
                else:
                    raise ValueError('cannot parse layer id: %s', id_)
        caret.dump_cell_color()
        caret.dump_cells()
        caret.dump_contours()



if __name__ == '__main__':
    main = Main(spacing=6.)
    #main.run('mf3r_SOLO CLAUSTRO')
    #main.run('(1bis)NM31claustroecellule')
    #main.run('(2)MF6soloclaustroconcellule')
    #main.run('MF10_claustroSolo')
    #main.run('MF4 Ros-Cauclaustro2')
    #main.run('mf3r_SOLO CLAUSTRO_x MIKI')
    main.run('(1bis)NM31claustroecellule')
