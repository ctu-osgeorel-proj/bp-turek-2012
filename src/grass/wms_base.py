import grass.script as grass
import xml.etree.ElementTree as etree
from urllib2 import urlopen

class WMS:

    def __init__(self):
        self.bboxes = []


    def run(self, options, flags):

        self.__initializeParameters(options, flags)
        self.__computeTiles()
	self.__downloadTiles()
	self.__createOutputMapFromTiles()


    def __initializeParameters(self, options, flags):

        self.o_mapserver_url = options['mapserver_url'] + "?"
        self.o_wms_version = options['wms_version']
 	self.f_no_check_param = flags["c"]

	if not self.f_no_check_param:
	    cap_xml = self.__getCapabilities()
            cap_xml_capability = cap_xml.find('Capability')

#	grass.message(_(etree.tostring(cap_xml_service, "utf-8")))
        self.o_layers = options['layers']
        self.o_styles = options['styles']
        self.o_srs = options['srs']
        self.o_map_res_x = options['map_res_x']
        self.o_map_res_y = options['map_res_y']
        self.o_output = options['output'] 
	cap_xml_service = cap_xml.find('Service')

   # check if given region exists      
	if options['region']:
            if not grass.find_file(name = options['region'], element = 'windows')['name']:
                grass.fatal(_("Region <%s> not found") % options['region'])

        # if the user asserts that this projection is the same as the
        # source use this projection as the source to get a trivial
        # tiling from r.tileset
     
        self.proj_srs = grass.read_command('g.proj', flags='j', epsg =self.o_srs )
        self.srs_scale = int((grass.parse_key_val(self.proj_srs))['+to_meter'])
      

    def __getCapabilities(self):

    # download capabilities file
        cap_url_param = "service=WMS&request=GetCapabilities&version=" + self.o_wms_version
        cap_url = self.o_mapserver_url + cap_url_param 
        try:
  		## TODO druhy argument funkce (mozna ulozeni souboru)
                cap_file = urlopen(cap_url, )
        except IOError:
            grass.fatal(_("Unable to get capabilities of '%s'") % self.o_mapserver_url)

   # check DOCTYPE first      
        if 'text/xml' not in cap_file.info()['content-type']:
            grass.fatal(_("Unable to get capabilities: %s") % cap_url)
        cap_xml = etree.parse(cap_file)
        cap_xml_service = cap_xml.find('Service')
	cap_xml_service_name = cap_xml_service.find('Name')
	if cap_xml_service_name.text != 'WMS':
            grass.fatal(_("Unable to get capabilities: %s") %  cap_url)		

	return cap_xml


    def __computeTiles(self):
   
	grass.message(_("Calculating tiles..."))
     
        if self.proj_srs ==  grass.read_command('g.proj', flags='j'):	
            region = grass.region()
            bbox = {'n': str(region['n']), 's': str(region['s']), 'e': str(region['e']), 'w': str(region['w']), 'rows': str(region['rows']), 'cols': str(region['cols']) }
            self.bboxes.append(bbox)
        else:
            tiles = grass.read_command('r.tileset',
                                flags = 'g',
                                sourceproj =  '+init=epsg:32633' ,
                                sourcescale = 1,
                                overlap = 2,
                                maxcols = 1000,
                                maxrows = 1000) ## TODO maxcols, maxrows

            tiles = tiles.splitlines()
            for tile in tiles:           
                dtile = grass.parse_key_val(tile, vsep=';')
                n = dtile['n']
                s = dtile['s']
                e = dtile['e']
                w = dtile['w']
                nr =dtile['rows']
                nc =dtile['cols']
   
                bbox = {'n': n, 's': s, 'e': e, 'w': w, 'rows': nr, 'cols': nc}
                self.bboxes.append(bbox)


    def __downloadTiles(self):

        gdal_wms = etree.Element("GDAL_WMS")
        service = etree.SubElement(gdal_wms, "Service")
        name = etree.Element("name")
        service.set("name","WMS")
        version = etree.SubElement(service, "Version")
        version.text =self.o_wms_version
        server_url = etree.SubElement(service, "ServerUrl")
        server_url.text =self.o_mapserver_url

        if self.o_wms_version == "1.1.1":
            srs = etree.SubElement(service, "SRS")
        elif self.o_wms_version == "1.3.0":
            srs = etree.SubElement(service, "CRS")
        else: 
            grass.error("Wrong wms_version")
        srs.text = 'EPSG:' + self.o_srs

        image_format = etree.SubElement(service, "ImageFormat")
        image_format.text = "image/jpeg"

        layers = etree.SubElement(service, "Layers")
        layers.text =self.o_layers

        styles = etree.SubElement(service, "Styles")
        styles.text =self.o_styles

        data_window = etree.SubElement(gdal_wms, "DataWindow")
    
        i = 1
        ##TODO jak prepsat obsah temfpile
        self.xml_file = grass.tempfile()
	for bbox in self.bboxes:

            upper_left_x = etree.SubElement(data_window, "UpperLeftX")
            upper_left_x.text = bbox['w'] #"197613"

            upper_left_y = etree.SubElement(data_window, "UpperLeftY")
            upper_left_y.text = bbox['n'] #"5784919"

            lower_right_x = etree.SubElement(data_window, "LowerRightX")
            lower_right_x.text = bbox['e'] #"891648"

            lower_right_y = etree.SubElement(data_window, "LowerRightY")
            lower_right_y.text = bbox['s'] #"5295313"

            size_x = etree.SubElement(data_window, "SizeX")
            size_x.text = "1000" #!! 

            size_y = etree.SubElement(data_window, "SizeY")
            size_y.text = "1000"

            block_size_x = etree.SubElement(gdal_wms, "BlockSizeX")
            block_size_x.text = "400"

            block_size_y = etree.SubElement(gdal_wms, "BlockSizeY")
            block_size_y.text = "300"

 
            if self.xml_file is None:
                grass.fatal("Unable to create temporary files")
            etree.ElementTree(gdal_wms).write(self.xml_file)
        
            #dataset = gdal.Open( filename, GA_ReadOnly )

             #TODO gdal PYTHON bindings, az pak se pouzije r.in.gdal
            if grass.run_command(
                'r.in.gdal',
                input = self.xml_file,
                output = self.o_output + '_tile_' + str(i),
                flags = 'k'
            ) != 0:
                grass.fatal(_('r.in.gdal failed'))
            i = i + 1
   
     
    def __createOutputMapFromTiles(self): 
    
        i = 1
	for bbox in self.bboxes:  
    
            #TODO spustit jen kdyz budou vraceny kanalay rgb  
            if grass.run_command(
                'r.composite',
                red =self.o_output + '_tile_' + str(i) + '.1',
                green =self.o_output + '_tile_' + str(i) + '.2',
                blue =self.o_output + '_tile_' + str(i) + '.3',
                output = self.o_output + '_tile_' + str(i)
            ) != 0:
                grass.fatal(_('r.composite failed'))

            i = i + 1
