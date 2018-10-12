#! -*- encoding: utf-8
import os, time, datetime, re
import csv
from collections import namedtuple

from lxml import etree
from svgpathparse import parsePath

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


class Main(object):
    def __init__(self):
        "initialize"
        self.ts = [t/5. for t in range(6)]

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

    def run(self):
        with open('mf3r_SOLO CLAUSTRO.svg', 'rb') as f:
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
        all_contours = []
        all_cells = []
        all_vertices = []
        for g in root.xpath('./svg:g', namespaces=nsmap):
            id_ = re.sub(r'_x([\da-fA-F][\da-fA-F])_', lambda match_o: chr(int(match_o.group(1), 16)), g.get('id'))
            id_ = id_.replace('_', ' ')
            print 'layer id', id_
            matches = re.search(r'(?:(\d+)([a-z]?))\s*.*$', id_)
            if matches:
                slide = matches.group(1)
                section_suffix = matches.group(2)
                depth = slide
                print matches.groups()
                for path in g.xpath('.//svg:path', namespaces=nsmap):
                    #print etree.tostring(path)
                    p = parsePath(path.get('d'))
                    stroke = path.get('stroke')
                    fill = path.get('fill')
                    #color = stroke or fill
                    #print color, p
                    if stroke == '#313185' or fill.lower() == '#00aeef':
                        vertices = self.get_vertices(p)
                        zipped = zip(*vertices)
                        center = (sum(zipped[0]) / len(zipped[0]), sum(zipped[1]) / len(zipped[1]))
                        #print 'cell', center
                        all_cells.append([id_, depth, center])
                        all_vertices.append((center[0], center[1]))
                    elif fill == '#313185':
                        pass
                    else:
                        contour_vertices = self.get_vertices(p)
                        #print 'contour', [('%.3f,%.3f' % c) for c in contour_vertices]
                        all_contours.append((id_, depth, contour_vertices))
                        all_vertices.extend(contour_vertices)
            else:
                raise ValueError('cannot parse layer id: %s', id_)

        x_series = [v[0] for v in all_vertices]
        y_series = [v[1] for v in all_vertices]
        print 'box', min(x_series), max(x_series), min(y_series), max(y_series)
        offset_x = (min(x_series) + max(x_series)) / 2
        offset_y = (min(y_series) + max(y_series)) / 2
        contours_data = []
        contours_data.extend([
            'BeginHeader',
            'Caret-Version 5.61',
            'date mer feb 3 18:29:18 2010',
            'encoding ASCII',
            'pubmed_id',
            'EndHeader',
            'tag-version 1',
            'tag-number-of-contours %s' % len(all_contours),
            'tag-section-spacing 0.2',
            'tag-BEGIN-DATA'
        ])
        cnt = 0
        for id_, depth, vertices in all_contours:
            contours_data.append('%s %s %s' % (cnt, len(vertices), depth))
            for p in vertices:
                contours_data.append('%s %s' % (p[0] - offset_x, offset_y - p[1]))
            cnt += 1

        with open('monash.contours', 'wb') as fout:
            fout.write('\n'.join(contours_data))
            fout.write('\n')

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
        cc.append(['mdplot.cell', '49', '49', '133', '255', '3.0', '1.0', 'POINT', ''])
        cc.append(['csvf-section-end', 'Colors', '', '', '', '', '', '', ''])
        with open('monash.contour_cell_color', 'wb') as fout:
            writer = csv.writer(fout)
            writer.writerows(cc)

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
        for idx, cell_tuple in enumerate(all_cells):
            id_, depth, vertices = cell_tuple
            cells.append([
                idx, vertices[0] - offset_x, offset_y - vertices[1], int(depth) * 0.2, depth, 'mdplot.cell', '', '', '', '', '', '', '', 'mdplot'
            ])
        cells.append(['csvf-section-end', 'Cells'])
        #fields = ['Cell_Number', 'X', 'Y', 'Z', 'Section', 'Name', 'Study_Number', 'Geography', 'Area', 'Size', 'Statistic',
        #     'Comment', 'Structure', 'Class_Name', 'SuMS_ID_Number', 'SuMS_Repeat_Number', 'SuMS_Parent_Cell_Base_ID',
        #     'SuMS_Version_Number', 'SuMS_MSLID', 'Attribute_ID', 'Study_PubMed_ID', 'Study_Table_Number',
        #     'Study_Table_Subheader', 'Study_Figure_Number', 'Study_Figure_Panel', 'Study_Page_Reference_Number',
        #     'Study_Page_Reference_Subheader']
        #MonashCell = namedtuple('MonashCell', fields)

        with open('monash.contour_cells', 'wb') as fout:
            writer = csv.writer(fout)
            writer.writerows(map(lambda l: l + ([''] * (27 - len(l))), cells))

if __name__ == '__main__':
    main = Main()
    main.run()
