def get_img_list():
    l = [
        "https://dap.ceda.ac.uk/neodc/sentinel_ard/data/sentinel_1/2018/06/01/S1B_20180601_132_asc_174823_174848_VVVH_G0_GB_OSGB_RTCK_SpkRL.tif",
        "https://dap.ceda.ac.uk/neodc/sentinel_ard/data/sentinel_1/2018/06/01/S1B_20180601_125_desc_063846_063911_VVVH_G0_GB_OSGB_RTCK_SpkRL.tif",
        "https://dap.ceda.ac.uk/neodc/sentinel_ard/data/sentinel_1/2018/06/01/S1B_20180601_132_asc_174913_174938_VVVH_G0_GB_OSGB_RTCK_SpkRL.tif",
        "https://dap.ceda.ac.uk/neodc/sentinel_ard/data/sentinel_1/2018/06/01/S1B_20180601_125_desc_063731_063756_VVVH_G0_GB_OSGB_RTCK_SpkRL.tif",
        "https://dap.ceda.ac.uk/neodc/sentinel_ard/data/sentinel_1/2018/06/01/S1B_20180601_125_desc_063616_063641_VVVH_G0_GB_OSGB_RTCK_SpkRL.tif",
        "https://dap.ceda.ac.uk/neodc/sentinel_ard/data/sentinel_1/2018/06/01/S1B_20180601_132_asc_175028_175053_VVVH_G0_GB_OSGB_RTCK_SpkRL.tif",
        "https://dap.ceda.ac.uk/neodc/sentinel_ard/data/sentinel_1/2018/06/01/S1B_20180601_132_asc_174938_175003_VVVH_G0_GB_OSGB_RTCK_SpkRL.tif",
        "https://dap.ceda.ac.uk/neodc/sentinel_ard/data/sentinel_1/2018/06/01/S1B_20180601_132_asc_175003_175028_VVVH_G0_GB_OSGB_RTCK_SpkRL.tif",
        "https://dap.ceda.ac.uk/neodc/sentinel_ard/data/sentinel_1/2018/06/01/S1B_20180601_125_desc_063641_063706_VVVH_G0_GB_OSGB_RTCK_SpkRL.tif",
        "https://dap.ceda.ac.uk/neodc/sentinel_ard/data/sentinel_1/2018/06/01/S1B_20180601_125_desc_063706_063731_VVVH_G0_GB_OSGB_RTCK_SpkRL.tif",
        "https://dap.ceda.ac.uk/neodc/sentinel_ard/data/sentinel_1/2018/06/01/S1B_20180601_132_asc_175053_175118_VVVH_G0_GB_OSGB_RTCK_SpkRL.tif",
        "https://dap.ceda.ac.uk/neodc/sentinel_ard/data/sentinel_1/2018/06/01/S1B_20180601_132_asc_175118_175143_VVVH_G0_GB_OSGB_RTCK_SpkRL.tif",
        "https://dap.ceda.ac.uk/neodc/sentinel_ard/data/sentinel_1/2018/06/01/S1B_20180601_132_asc_174848_174913_VVVH_G0_GB_OSGB_RTCK_SpkRL.tif",
        "https://dap.ceda.ac.uk/neodc/sentinel_ard/data/sentinel_1/2018/06/01/S1B_20180601_125_desc_063911_063936_VVVH_G0_GB_OSGB_RTCK_SpkRL.tif",
        "https://dap.ceda.ac.uk/neodc/sentinel_ard/data/sentinel_1/2018/06/01/S1B_20180601_125_desc_063756_063821_VVVH_G0_GB_OSGB_RTCK_SpkRL.tif",
    ]
    l.sort()
    return l


def get_feature_links():
    d = {
        1: [
            "https://dap.ceda.ac.uk/neodc/sentinel_ard/data/sentinel_1/2018/06/01/S1B_20180601_132_asc_175028_175053_VVVH_G0_GB_OSGB_RTCK_SpkRL.tif",
            "https://dap.ceda.ac.uk/neodc/sentinel_ard/data/sentinel_1/2018/06/01/S1B_20180601_132_asc_175003_175028_VVVH_G0_GB_OSGB_RTCK_SpkRL.tif",
            "https://dap.ceda.ac.uk/neodc/sentinel_ard/data/sentinel_1/2018/06/01/S1B_20180601_125_desc_063706_063731_VVVH_G0_GB_OSGB_RTCK_SpkRL.tif",
        ],
        2: [
            "https://dap.ceda.ac.uk/neodc/sentinel_ard/data/sentinel_1/2018/06/01/S1B_20180601_125_desc_063731_063756_VVVH_G0_GB_OSGB_RTCK_SpkRL.tif",
            "https://dap.ceda.ac.uk/neodc/sentinel_ard/data/sentinel_1/2018/06/01/S1B_20180601_132_asc_175003_175028_VVVH_G0_GB_OSGB_RTCK_SpkRL.tif",
            "https://dap.ceda.ac.uk/neodc/sentinel_ard/data/sentinel_1/2018/06/01/S1B_20180601_125_desc_063756_063821_VVVH_G0_GB_OSGB_RTCK_SpkRL.tif",
        ],
    }
    d = {k: sorted(v) for k, v in d.items()}
    return d
