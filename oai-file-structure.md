```
openairinterface5g/
├── CHANGELOG.md
├── CMakeLists.txt
├── CMakePresets.json
├── CONTRIBUTING.md
├── LICENSE
├── LICENSES
│   ├── deprecated
│   │   └── OAI-PL-v1.1.txt
│   ├── exception
│   │   ├── Apache-2.0.txt
│   │   ├── BSD-2-Clause.txt
│   │   └── BSD-3-Clause.txt
│   └── preferred
│       ├── CC-BY-4.0.txt
│       ├── CSSL-v1.0.txt
│       └── MIT.txt
├── NOTICE
├── README.md
├── charts
│   ├── physims-4g
│   │   ├── Chart.yaml
│   │   ├── charts
│   │   │   └── physims.4g
│   │   │       ├── Chart.yaml
│   │   │       ├── templates
│   │   │       │   ├── _helpers.tpl
│   │   │       │   └── job.yaml
│   │   │       └── values.yaml
│   │   ├── templates
│   │   │   ├── rbac.yaml
│   │   │   └── serviceaccount.yaml
│   │   └── values.yaml
│   └── physims-5g
│       ├── Chart.yaml
│       ├── charts
│       │   └── physims.5g
│       │       ├── Chart.yaml
│       │       ├── templates
│       │       │   ├── _helpers.tpl
│       │       │   └── job.yaml
│       │       └── values.yaml
│       ├── templates
│       │   ├── rbac.yaml
│       │   └── serviceaccount.yaml
│       └── values.yaml
├── ci-scripts
│   ├── Jenkinsfile
│   ├── Jenkinsfile-GitLab-Container
│   ├── Jenkinsfile-colosseum
│   ├── Jenkinsfile-push-local-repo
│   ├── Jenkinsfile-push-registry
│   ├── Jenkinsfile-scheduled-run
│   ├── README.md
│   ├── args_parse.py
│   ├── as_ue
│   │   ├── aw2s-asue.cfg
│   │   ├── aw2s-multi-00102-20.cfg
│   │   ├── aw2s-multi-00102-2x2-v2.cfg
│   │   ├── config.cfg
│   │   ├── multi-00105-100.cfg
│   │   └── multi-00105-40.cfg
│   ├── attenuatorctl.py
│   ├── checkAddedWarnings.sh
│   ├── checkCodingFormattingRules.sh
│   ├── checkGitLabMergeRequestLabels.sh
│   ├── ci_ctl_adb.sh
│   ├── ci_ctl_qtel.py
│   ├── ci_infra.yaml
│   ├── cls_analysis.py
│   ├── cls_ci_helper.py
│   ├── cls_cluster.py
│   ├── cls_cmd.py
│   ├── cls_containerize.py
│   ├── cls_corenetwork.py
│   ├── cls_loganalysis.py
│   ├── cls_module.py
│   ├── cls_native.py
│   ├── cls_oai_html.py
│   ├── cls_oaicitest.py
│   ├── cls_static_code_analysis.py
│   ├── colosseum_scripts
│   │   ├── README.md
│   │   ├── check-results.sh
│   │   ├── get-test-results.sh
│   │   ├── launch-job.sh
│   │   ├── set-job-status.sh
│   │   └── wait-job-end.sh
│   ├── conf_files
│   │   ├── README.md
│   │   ├── channelmod_rfsimu.conf
│   │   ├── enb-rcc.band40.25prb.tm1.if4p5.fair-scheduler.conf
│   │   ├── enb-rcc.band7.25prb.tm1.if4p5.conf
│   │   ├── enb-rru.band40.usrpb210.tm1.conf
│   │   ├── enb-rru.band7.usrpb210.tm1.conf
│   │   ├── enb.band38.25prb.rfsim.conf
│   │   ├── enb.band38.lte_2x2.100prb.usrpn310.conf
│   │   ├── enb.band38.lte_2x2_tm2.100prb.usrpn310.conf
│   │   ├── enb.band40.100prb.usrpb200.tm1-defaultscheduler.conf
│   │   ├── enb.band40.25prb.usrpb200.conf
│   │   ├── enb.band7.100prb.rfsim.conf
│   │   ├── enb.band7.100prb.usrpb200.tm1.conf
│   │   ├── enb.band7.25prb.l2sim.conf
│   │   ├── enb.band7.25prb.rfsim.conf
│   │   ├── enb.band7.25prb.rfsim.nos1.conf
│   │   ├── enb.band7.25prb.usrpb200.conf
│   │   ├── enb.band7.25prb.usrpb200.tm1-norrc.conf
│   │   ├── enb.band7.25prb.usrpb200.tm1.conf
│   │   ├── enb.band7.50prb.rfsim.conf
│   │   ├── enb.band7.50prb.usrpb200.tm1.conf
│   │   ├── enb.band7.tm1.25prb.rfsim.mbms.conf
│   │   ├── enb.nsa.band7.25prb.usrpb200.conf
│   │   ├── gnb-cu.sa.band78.106prb.conf
│   │   ├── gnb-cu.sa.f1.conf
│   │   ├── gnb-cu.sa.f1.ho.conf
│   │   ├── gnb-cucp.sa.e1-ho-n2.conf
│   │   ├── gnb-cucp.sa.f1.conf
│   │   ├── gnb-cucp.sa.f1.quectel.conf
│   │   ├── gnb-cuup.sa.f1.conf
│   │   ├── gnb-cuup.sa.f1.quectel.conf
│   │   ├── gnb-du.sa.band1.52prb.usrpb210.conf
│   │   ├── gnb-du.sa.band77.273prb.fhi72.4x4-4L-vvdn.conf
│   │   ├── gnb-du.sa.band78.106prb.rfsim.conf
│   │   ├── gnb-du.sa.band78.106prb.usrpb200.conf
│   │   ├── gnb-du.sa.band78.273prb.fhi72.4x4-4L-benetel550.conf
│   │   ├── gnb-du.sa.band78.273prb.fhi72.4x4-4L-liteon.conf
│   │   ├── gnb-du.sa.band78.273prb.fhi72.4x4-4L-metanoia.conf
│   │   ├── gnb-du.sa.band78.273prb.fhi72.8x8-benetel650_650.conf
│   │   ├── gnb-du.sa.band78.51prb.usrpb210.ho-pci0.conf
│   │   ├── gnb-du.sa.band78.51prb.usrpb210.ho-pci1.conf
│   │   ├── gnb-pnf.band66.rfsim.conf
│   │   ├── gnb-pnf.band77.usrpn310.4x4.conf
│   │   ├── gnb-pnf.sa.band77.273prb.fhi72.4x4-4L-vvdn.conf
│   │   ├── gnb-vnf.sa.band66.u0.25prb.nfapi.conf
│   │   ├── gnb-vnf.sa.band77.162prb.nfapi.4x4.conf
│   │   ├── gnb-vnf.sa.band77.273prb.fhi72.4x4-4L-vvdn.conf
│   │   ├── gnb-vnf.sa.band78.273prb.aerial.conf
│   │   ├── gnb-vnf.sa.band78.273prb.aerial.ul-heavy.conf
│   │   ├── gnb-vnf.sa.band78.78prb.aerial.conf
│   │   ├── gnb.band66.106prb.rfsim.phytest-dora.conf
│   │   ├── gnb.band77.273prb.fhi72.4x4-vvdn-phytest.conf
│   │   ├── gnb.band78.106prb.rfsim.phytest-dora.conf
│   │   ├── gnb.band79.106prb.usrpn300.phytest-dora.conf
│   │   ├── gnb.band79.162prb.usrpn300.phytest-dora.conf
│   │   ├── gnb.band79.273prb.usrpn300.phytest-dora.conf
│   │   ├── gnb.nsa.band78.106prb.usrpb200.conf
│   │   ├── gnb.sa.band254.u0.25prb.rfsim.ntn-leo.conf
│   │   ├── gnb.sa.band254.u0.25prb.rfsim.ntn.conf
│   │   ├── gnb.sa.band257.u3.66prb.rfsim.conf
│   │   ├── gnb.sa.band66.106prb.rfsim.conf
│   │   ├── gnb.sa.band77.162prb.usrpn310.2x2.conf
│   │   ├── gnb.sa.band77.273prb.fhi72.4x4-4layers-vvdn.conf
│   │   ├── gnb.sa.band77.273prb.fhi72.4x4-vvdn.conf
│   │   ├── gnb.sa.band77.273prb.usrpn310.2x2.conf
│   │   ├── gnb.sa.band77.51prb.usrpb200.n2-ho.conf
│   │   ├── gnb.sa.band78.106prb.fhi72.4x4-benetel550-9b-mplane.conf
│   │   ├── gnb.sa.band78.106prb.n310.7ds2u.conf
│   │   ├── gnb.sa.band78.106prb.rfsim.conf
│   │   ├── gnb.sa.band78.106prb.rfsim.flexric.conf
│   │   ├── gnb.sa.band78.106prb.rfsim.neighbour.conf
│   │   ├── gnb.sa.band78.106prb.rfsim.prs.conf
│   │   ├── gnb.sa.band78.106prb.rfsim.yaml
│   │   ├── gnb.sa.band78.106prb.usrpb200.sc-fdma-deltaMCS.conf
│   │   ├── gnb.sa.band78.106prb.vrtsim.2x2.yaml
│   │   ├── gnb.sa.band78.24prb.rfsim.conf
│   │   ├── gnb.sa.band78.273prb.fhi72.2x2-benetel550-9b-mplane.conf
│   │   ├── gnb.sa.band78.273prb.rfsim.2x2.conf
│   │   ├── gnb.sa.band78.51prb.aw2s.ddsuu.2x2.conf
│   │   ├── gnb.sa.band78.51prb.aw2s.ddsuu.conf
│   │   ├── gnb.sa.band78.51prb.usrpb200.conf
│   │   ├── lte-ue.usim.conf
│   │   ├── lteue.band7.25prb.l2sim.conf
│   │   ├── lteue.rfsim.conf
│   │   ├── lteue.usim-ci-magma.conf
│   │   ├── lteue.usim-ci.conf
│   │   ├── lteue.usim-mbs.conf
│   │   ├── neighbour-config-ho.conf
│   │   ├── neighbour-config.conf
│   │   ├── nrue.band78.106prb.l2sim.conf
│   │   ├── nrue.band78.106prb.prs.conf
│   │   ├── nrue.uicc.2pdu.conf
│   │   ├── nrue.uicc.conf
│   │   ├── nrue.uicc.ntn-leo.conf
│   │   ├── nrue.uicc.yaml
│   │   ├── nrue.vrtsim.chanmod.yaml
│   │   ├── ue.sa.conf
│   │   └── untested
│   │       ├── benetel-4g.conf
│   │       ├── benetel-5g.conf
│   │       ├── enb.band13.tm1.25PRB.usrpb210.conf
│   │       ├── enb.band13.tm1.50PRB.emtc.conf
│   │       ├── enb.band17.tm1.25PRB.usrpb210.conf
│   │       ├── enb.band17.tm1.mbms.25PRB.usrpb210.conf
│   │       ├── enb.band38.nsa_2x2.100prb.usrpn310.conf
│   │       ├── enb.band40.tm1.100PRB.FairScheduler.usrpb210.conf
│   │       ├── enb.band40.tm1.25PRB.FairScheduler.usrpb210.conf
│   │       ├── enb.band40.tm1.50PRB.FairScheduler.usrpb210.conf
│   │       ├── enb.band40.tm2.25PRB.FairScheduler.usrpb210.conf
│   │       ├── enb.band7.tm1.100PRB.usrpb210.conf
│   │       ├── enb.band7.tm1.25PRB.slave.usrpb210.conf
│   │       ├── enb.band7.tm1.25PRB.usrpb210.conf
│   │       ├── enb.band7.tm1.50prb.usrpb210.conf
│   │       ├── enb.band7.tm1.fr1.25PRB.usrpb210.conf
│   │       ├── enb.band7.tm2.25PRB.usrpb210.conf
│   │       ├── enb.slave.band13.tm1.25PRB.usrpb210.conf
│   │       ├── episci
│   │       │   ├── episci_nr-ue.nfapi.conf
│   │       │   ├── episci_rcc.band7.tm1.nfapi.conf
│   │       │   ├── episci_rcc.band78.tm1.106PRB.nfapi.conf
│   │       │   ├── episci_ue.nfapi.conf
│   │       │   ├── episci_ue_test_sfr.conf
│   │       │   ├── gnb_band78.sa.fr1.106PRB.2x2.l2sim.conf
│   │       │   ├── proxy_nr-ue.nfapi.conf
│   │       │   ├── proxy_rcc.band7.tm1.nfapi.conf
│   │       │   ├── proxy_rcc.band78.tm1.106PRB.nfapi.conf
│   │       │   └── proxy_ue.nfapi.conf
│   │       ├── gNB_SA_n78_106PRB.2x2_usrpn310.conf
│   │       ├── gNB_SA_n78_133PRB.2x2_usrpn310.conf
│   │       ├── gnb.band78.sa.fr1.106PRB.usrpn310.conf
│   │       ├── gnb.band78.tm1.fr1.106PRB.usrpb210.conf
│   │       ├── gnb.band78.tm1.fr1.106PRB.usrpn310.conf
│   │       ├── gnb.nsa.band78.106prb.usrpn310.2x2.conf
│   │       ├── gnb.sa.band66.fr1.106PRB.usrpn300.conf
│   │       ├── gnb.sa.band78.106prb.usrp310.2x2.conf
│   │       ├── gnb.sa.band78.106prb.usrpn310.ddsuu-2x2.conf
│   │       ├── gnb.sa.band78.162prb.usrpn310.2x2.conf
│   │       ├── gnb.sa.band78.fr1.51PRB.usrpb210.conf
│   │       ├── lte-tdd-basic-sim.conf
│   │       ├── proxy_gnb.band78.sa.fr1.106PRB.usrpn310.conf
│   │       ├── rcc.band38.tm1.50PRB.multi.rru.conf
│   │       ├── rcc.band7.tm1.mbms-s1ap.if4p5.50PRB.lo.conf
│   │       ├── rcc.band7.tm1.mbms.if4p5.50PRB.lo.conf
│   │       ├── rcc.band7.tm1.nfapi.conf
│   │       ├── rru.band38.tm1.master.conf
│   │       └── rru.band38.tm1.slave.conf
│   ├── constants.py
│   ├── datalog_rt_stats.100.2x2.fhi72.cacofonix.yaml
│   ├── datalog_rt_stats.100.2x2.yaml
│   ├── datalog_rt_stats.100.4x4.fhi72.yaml
│   ├── datalog_rt_stats.1x1.60.yaml
│   ├── datalog_rt_stats.2x2.yaml
│   ├── datalog_rt_stats.60.2x2.yaml
│   ├── datalog_rt_stats.default.yaml
│   ├── docker
│   │   ├── Dockerfile.build.optional.ubuntu
│   │   ├── Dockerfile.channelsim.ubuntu
│   │   ├── Dockerfile.formatting.ubuntu
│   │   ├── Dockerfile.physim.cuda.ubuntu
│   │   ├── Dockerfile.physim.ubuntu
│   │   ├── Dockerfile.unittest.cuda.ubuntu
│   │   └── Dockerfile.unittest.ubuntu
│   ├── fail.sh
│   ├── helpreadme.py
│   ├── main.py
│   ├── mbim_scripts
│   │   ├── mbim-set-ip.sh
│   │   ├── start_quectel_mbim.sh
│   │   └── stop_quectel_mbim.sh
│   ├── pre-ci-check.sh
│   ├── provideUniqueImageTag.py
│   ├── ran.py
│   ├── run_locally.sh
│   ├── scripts
│   │   ├── create_workspace.sh
│   │   ├── docker-build-and-deploy-chansim.sh
│   │   ├── docker-build-and-deploy-physims-cuda.sh
│   │   ├── docker-build-and-deploy-physims.sh
│   │   ├── magma-epc-deploy.sh
│   │   ├── magma-epc-logcollect.sh
│   │   ├── oc-chart-deploy.sh
│   │   ├── oc-chart-undeploy.sh
│   │   ├── oc-cn5g-deploy.sh
│   │   ├── oc-cn5g-logcollect.sh
│   │   ├── oc-cn5g-undeploy.sh
│   │   ├── oc-deploy-physims.sh
│   │   ├── set-and-verify-distance-prs.sh
│   │   ├── set-wnc-bandwidth.sh
│   │   ├── source-deploy-physims.sh
│   │   ├── sys-info.sh
│   │   ├── vvdn-activate-carriers.sh
│   │   └── vvdn-inactivate-carriers.sh
│   ├── tests
│   │   ├── README.md
│   │   ├── analysis
│   │   │   ├── gnb_phytest.success.nrL1.log
│   │   │   └── gnb_phytest.success.nrMAC.log
│   │   ├── analysis.py
│   │   ├── build.py
│   │   ├── cmd.py
│   │   ├── config
│   │   │   ├── infra_ping_iperf.yaml
│   │   │   ├── test_core_infra.yaml
│   │   │   └── test_module_infra.yaml
│   │   ├── corenetwork.py
│   │   ├── deployment.py
│   │   ├── iperf-analysis.py
│   │   ├── log
│   │   │   ├── iperf_udp_msg_nok.txt
│   │   │   ├── iperf_udp_msg_nok2.txt
│   │   │   ├── iperf_udp_msg_nok3.txt
│   │   │   ├── iperf_udp_msg_ok.txt
│   │   │   ├── iperf_udp_msg_ok2.txt
│   │   │   ├── iperf_udp_test_nok.log
│   │   │   ├── iperf_udp_test_nok2.log
│   │   │   ├── iperf_udp_test_nok3.log
│   │   │   ├── iperf_udp_test_ok.log
│   │   │   ├── iperf_udp_test_ok2.log
│   │   │   ├── iperf_udp_v2_ok.log
│   │   │   └── iperf_udp_v2_ok.txt
│   │   ├── log-analysis
│   │   │   ├── arbitrary.log
│   │   │   ├── empty.log
│   │   │   ├── retx-check-bad.log
│   │   │   ├── retx-check-good.log
│   │   │   └── with-bye.log
│   │   ├── log-analysis.py
│   │   ├── module.py
│   │   ├── ping-iperf.py
│   │   ├── pull-clean-int-registry.py
│   │   ├── script-deployment.py
│   │   ├── scripts
│   │   │   ├── deploy-core.sh
│   │   │   ├── deploy-with-script.sh
│   │   │   ├── hello-fail.sh
│   │   │   ├── hello-world.sh
│   │   │   └── undeploy-with-script.sh
│   │   ├── simple-dep
│   │   │   └── docker-compose.yml
│   │   ├── simple-fail
│   │   │   └── docker-compose.yml
│   │   ├── simple-fail-2svc
│   │   │   └── docker-compose.yml
│   │   ├── simple-undep
│   │   │   └── docker-compose.yml
│   │   └── test-runner
│   │       ├── run.sh
│   │       └── test.xml
│   ├── xml_class_list.yml
│   ├── xml_files
│   │   ├── cluster_image_build.xml
│   │   ├── container_4g_l2sim_tdd.xml
│   │   ├── container_4g_rfsim_fdd_05MHz.xml
│   │   ├── container_4g_rfsim_fdd_05MHz_noS1.xml
│   │   ├── container_4g_rfsim_fdd_10MHz.xml
│   │   ├── container_4g_rfsim_fdd_20MHz.xml
│   │   ├── container_4g_rfsim_fembms.xml
│   │   ├── container_4g_rfsim_mbms.xml
│   │   ├── container_4g_rfsim_tdd_05MHz.xml
│   │   ├── container_5g_e1_rfsim.xml
│   │   ├── container_5g_f1_rfsim.xml
│   │   ├── container_5g_fdd_rfsim.xml
│   │   ├── container_5g_flexric_rfsim.xml
│   │   ├── container_5g_rfsim.xml
│   │   ├── container_5g_rfsim_24prb.xml
│   │   ├── container_5g_rfsim_2x2.xml
│   │   ├── container_5g_rfsim_fdd_phytest.xml
│   │   ├── container_5g_rfsim_fr2_66prb.xml
│   │   ├── container_5g_rfsim_multiue.xml
│   │   ├── container_5g_rfsim_n2_ho.xml
│   │   ├── container_5g_rfsim_ntn_geo.xml
│   │   ├── container_5g_rfsim_ntn_leo.xml
│   │   ├── container_5g_rfsim_prs.xml
│   │   ├── container_5g_rfsim_sidelink.xml
│   │   ├── container_5g_rfsim_simple.xml
│   │   ├── container_5g_rfsim_tdd_dora.xml
│   │   ├── container_5g_rfsim_u0_25prb.xml
│   │   ├── container_5g_vrtsim_chanmod.xml
│   │   ├── container_5g_vrtsim_chanmod_gh.xml
│   │   ├── container_5g_vrtsim_cirdb.xml
│   │   ├── container_5g_vrtsim_multiue_gh.xml
│   │   ├── container_5g_zmq_2x2.xml
│   │   ├── container_5g_zmq_ocudu_1x1.xml
│   │   ├── container_5g_zmq_ocudu_2x2.xml
│   │   ├── container_build_run_gh_tests.xml
│   │   ├── container_build_run_tests.xml
│   │   ├── container_image_build.xml
│   │   ├── container_image_build_arm.xml
│   │   ├── container_image_build_cross.xml
│   │   ├── container_image_build_jetson.xml
│   │   ├── container_image_build_t2.xml
│   │   ├── container_lte_b200_fdd_05Mhz_tm1.xml
│   │   ├── container_lte_b200_fdd_05Mhz_tm1_if4_5.xml
│   │   ├── container_lte_b200_fdd_05Mhz_tm1_no_rrc_activity.xml
│   │   ├── container_lte_b200_fdd_10Mhz_tm1.xml
│   │   ├── container_lte_b200_fdd_10Mhz_tm1_cdrx.xml
│   │   ├── container_lte_b200_fdd_10Mhz_tm1_oaiue.xml
│   │   ├── container_lte_b200_fdd_20Mhz_tm1.xml
│   │   ├── container_lte_b200_tdd_05Mhz_tm1.xml
│   │   ├── container_lte_b200_tdd_05Mhz_tm1_if4_5.xml
│   │   ├── container_lte_b200_tdd_10Mhz_tm1.xml
│   │   ├── container_lte_b200_tdd_20Mhz_tm1.xml
│   │   ├── container_lte_b200_tdd_20Mhz_tm1_default_scheduler.xml
│   │   ├── container_lte_n3xx_tdd_2x2_tm1.xml
│   │   ├── container_lte_n3xx_tdd_2x2_tm2.xml
│   │   ├── container_nsa_b200_quectel.xml
│   │   ├── container_sa_aerial_cn_start.xml
│   │   ├── container_sa_aerial_cn_stop.xml
│   │   ├── container_sa_aerial_quectel.xml
│   │   ├── container_sa_aerial_quectel_ul_heavy.xml
│   │   ├── container_sa_aw2s_asue.xml
│   │   ├── container_sa_aw2s_asue_2x2.xml
│   │   ├── container_sa_b200_nrue_jetson.xml
│   │   ├── container_sa_b200_quectel.xml
│   │   ├── container_sa_e1_b200_quectel.xml
│   │   ├── container_sa_f1_b200_quectel.xml
│   │   ├── container_sa_f1_ho_b210_quectel.xml
│   │   ├── container_sa_fhi72_benetel_2x2_100MHz_9b_mplane_amariue.xml
│   │   ├── container_sa_fhi72_benetel_4x4_40MHz_9b_mplane_amariue.xml
│   │   ├── container_sa_fhi72_benetel_4x4_up2.xml
│   │   ├── container_sa_fhi72_benetel_8x8_up3.xml
│   │   ├── container_sa_fhi72_liteon_4x4_up2.xml
│   │   ├── container_sa_fhi72_metanoia_4x4_up2.xml
│   │   ├── container_sa_fhi72_vvdn_4x4_monolithic_up2.xml
│   │   ├── container_sa_fhi72_vvdn_4x4_up2.xml
│   │   ├── container_sa_fhi72_vvdn_4x4_up2_nfapi.xml
│   │   ├── container_sa_fhi72_vvdn_up2.xml
│   │   ├── container_sa_n2_ho_b210_quectel.xml
│   │   ├── container_sa_n310_2X2_100MHz_quectel.xml
│   │   ├── container_sa_n310_2X2_60MHz_quectel.xml
│   │   ├── container_sa_n310_4X4_60MHz_quectel.xml
│   │   ├── container_sa_n310_nrue.xml
│   │   ├── container_sa_n310_nrue_longrun.xml
│   │   ├── container_sa_sc_b200_quectel.xml
│   │   ├── formatting_check.xml
│   │   ├── fr1_5gc_closure.xml
│   │   ├── fr1_5gc_start.xml
│   │   ├── fr1_cn5g_basic_deploy.xml
│   │   ├── fr1_cn5g_basic_undeploy.xml
│   │   ├── fr1_epc_closure.xml
│   │   ├── fr1_epc_start.xml
│   │   ├── fr1_epc_start_verizon.xml
│   │   ├── fr1_oai_cn_deploy.xml
│   │   ├── fr1_oai_cn_undeploy.xml
│   │   ├── gnb_phytest_fhi7.2_docker.xml
│   │   ├── gnb_phytest_fhi7.2_docker_cacofonix.xml
│   │   ├── gnb_phytest_rfemulator_run_100_2x2.xml
│   │   ├── gnb_phytest_usrp_run.xml
│   │   ├── gnb_phytest_usrp_run_100_2x2.xml
│   │   ├── gnb_phytest_usrp_run_60.xml
│   │   ├── gnb_phytest_usrp_run_60_2x2.xml
│   │   ├── gnb_usrp_build.xml
│   │   ├── lte_oai_cn_deploy.xml
│   │   ├── lte_oai_cn_undeploy.xml
│   │   ├── physim_4g_deploy_run.xml
│   │   ├── physim_5g_deploy_run.xml
│   │   ├── physim_gracehopper.xml
│   │   ├── physim_timed_gracehopper.xml
│   │   ├── sa_cn5g_20897_closure.xml
│   │   ├── sa_cn5g_20897_start.xml
│   │   ├── sa_cn5g_closure.xml
│   │   ├── sa_cn5g_start.xml
│   │   ├── t2_offload_physim_enc_dec.xml
│   │   ├── test_channel_sim_gracehopper.xml
│   │   └── test_physim_cuda_gracehopper.xml
│   └── yaml_files
│       ├── 4g_l2sim_fdd
│       │   └── docker-compose.yml
│       ├── 4g_rfsimulator_fdd_05MHz
│       │   ├── README.md
│       │   ├── docker-compose.yml
│       │   ├── entrypoint.sh
│       │   ├── mme.conf
│       │   ├── mme_fd.sprint.conf
│       │   ├── oai_db.cql
│       │   └── redis_extern.conf
│       ├── 4g_rfsimulator_fdd_05MHz_noS1
│       │   └── docker-compose.yml
│       ├── 4g_rfsimulator_fdd_10MHz
│       │   └── docker-compose.yml
│       ├── 4g_rfsimulator_fdd_20MHz
│       │   └── docker-compose.yml
│       ├── 4g_rfsimulator_fembms
│       │   └── docker-compose.yml
│       ├── 4g_rfsimulator_mbms
│       │   └── docker-compose.yml
│       ├── 4g_rfsimulator_tdd_05MHz
│       │   └── docker-compose.yml
│       ├── 5g_f1_rfsimulator
│       │   └── docker-compose.yaml
│       ├── 5g_fdd_rfsimulator
│       │   └── docker-compose.yaml
│       ├── 5g_rfsimulator
│       │   ├── README.md
│       │   ├── docker-compose.yaml
│       │   ├── local-override-ue-gdb.yaml
│       │   ├── local-override.yaml
│       │   ├── mini_nonrf_config.yaml
│       │   ├── mysql-healthcheck.sh
│       │   ├── oai-end-to-end.jpg
│       │   └── oai_db.sql
│       ├── 5g_rfsimulator_24prb
│       │   └── docker-compose.yaml
│       ├── 5g_rfsimulator_2x2
│       │   └── docker-compose.yaml
│       ├── 5g_rfsimulator_e1
│       │   ├── README.md
│       │   ├── docker-compose.yaml
│       │   └── mini_nonrf_config_3slices.yaml
│       ├── 5g_rfsimulator_fdd_phytest
│       │   └── docker-compose.yaml
│       ├── 5g_rfsimulator_flexric
│       │   ├── conf
│       │   │   └── flexric.conf
│       │   └── docker-compose.yml
│       ├── 5g_rfsimulator_fr2_66prb
│       │   └── docker-compose.yaml
│       ├── 5g_rfsimulator_multiue
│       │   ├── docker-compose.yaml
│       │   └── nrue.uicc.conf
│       ├── 5g_rfsimulator_n2_ho
│       │   └── docker-compose.yaml
│       ├── 5g_rfsimulator_ntn_geo
│       │   └── docker-compose.yaml
│       ├── 5g_rfsimulator_ntn_leo
│       │   └── docker-compose.yaml
│       ├── 5g_rfsimulator_prs
│       │   └── docker-compose.yaml
│       ├── 5g_rfsimulator_sidelink
│       │   └── docker-compose.yaml
│       ├── 5g_rfsimulator_tdd_dora
│       │   ├── docker-compose.yaml
│       │   └── local-override.yaml
│       ├── 5g_rfsimulator_u0_25prb
│       │   ├── docker-compose.yaml
│       │   └── policies
│       │       ├── pcc_rules
│       │       │   └── pcc_rules.yaml
│       │       ├── policy_decisions
│       │       │   └── policy_decision.yaml
│       │       └── qos_data
│       │           └── qos_data.yaml
│       ├── 5g_sa_f1_b210_ho
│       │   └── docker-compose.yml
│       ├── 5g_sa_n2_ho_b210
│       │   └── docker-compose.yml
│       ├── 5g_sa_n310_2x2_100MHz
│       │   └── docker-compose.yml
│       ├── 5g_sa_n310_2x2_60MHz
│       │   └── docker-compose.yml
│       ├── 5g_sa_n310_4x4_60MHz
│       │   └── docker-compose.yml
│       ├── 5g_sa_n310_gnb
│       │   └── docker-compose.yml
│       ├── 5g_sa_n310_nrue
│       │   └── docker-compose.yml
│       ├── 5g_vrtsim_chanmod
│       │   └── docker-compose.yaml
│       ├── 5g_vrtsim_cirdb
│       │   └── docker-compose.yaml
│       ├── 5g_vrtsim_multiue
│       │   └── docker-compose.yaml
│       ├── 5g_zmq_radio_1x1_ocudu
│       │   ├── docker-compose.yaml
│       │   └── ocudu.yml
│       ├── 5g_zmq_radio_2x2
│       │   └── docker-compose.yaml
│       ├── 5g_zmq_radio_2x2_ocudu
│       │   ├── docker-compose.yaml
│       │   └── ocudu.yml
│       ├── fr1_epc_20897
│       │   ├── docker-compose.yml
│       │   ├── entrypoint.sh
│       │   └── mme.conf
│       ├── local_common_overrides
│       │   ├── build_images.yaml
│       │   └── rebuild_nr_softmodems.yaml
│       ├── lte_b200_fdd_05Mhz_if4.5
│       │   └── docker-compose.yml
│       ├── lte_b200_fdd_05Mhz_tm1
│       │   └── docker-compose.yml
│       ├── lte_b200_fdd_05Mhz_tm1_no_rrc_activity
│       │   └── docker-compose.yml
│       ├── lte_b200_fdd_10Mhz_oai_ue_magma
│       │   └── docker-compose.yml
│       ├── lte_b200_fdd_10Mhz_tm1
│       │   └── docker-compose.yml
│       ├── lte_b200_fdd_10Mhz_tm1_cdrx
│       │   └── docker-compose.yml
│       ├── lte_b200_fdd_10Mhz_tm1_magma
│       │   └── docker-compose.yml
│       ├── lte_b200_fdd_20Mhz_tm1
│       │   └── docker-compose.yml
│       ├── lte_b200_tdd_05Mhz_if4.5
│       │   └── docker-compose.yml
│       ├── lte_b200_tdd_05Mhz_tm1
│       │   └── docker-compose.yml
│       ├── lte_b200_tdd_05Mhz_tm2
│       │   └── docker-compose.yml
│       ├── lte_b200_tdd_10Mhz_tm1
│       │   └── docker-compose.yml
│       ├── lte_b200_tdd_20Mhz_tm1
│       │   └── docker-compose.yml
│       ├── lte_b200_tdd_20Mhz_tm1_default_scheduler
│       │   └── docker-compose.yml
│       ├── lte_n3xx_tdd_2x2_tm1
│       │   └── docker-compose.yml
│       ├── lte_n3xx_tdd_2x2_tm2
│       │   └── docker-compose.yml
│       ├── magma_lte_20892
│       │   ├── docker-compose.yml
│       │   ├── entrypoint.sh
│       │   ├── mme.conf
│       │   ├── mme_fd.sprint.conf
│       │   └── redis_extern.conf
│       ├── magma_nsa_20897
│       │   ├── docker-compose.yml
│       │   ├── entrypoint.sh
│       │   ├── mme.conf
│       │   ├── mme_fd.sprint.conf
│       │   ├── oai_db.cql
│       │   └── redis_extern.conf
│       ├── nsa_b200_enb
│       │   └── docker-compose.yml
│       ├── nsa_b200_gnb
│       │   └── docker-compose.yml
│       ├── phytest_fhi72
│       │   ├── docker-compose.yaml
│       │   └── setup_sriov_dummy.sh
│       ├── phytest_fhi72_cacofonix
│       │   ├── docker-compose.yaml
│       │   ├── setup_cleanup.sh
│       │   ├── setup_config.sh
│       │   └── setup_sriov_dummy.sh
│       ├── sa_aw2s_2x2_gnb
│       │   └── docker-compose.yml
│       ├── sa_aw2s_gnb
│       │   └── docker-compose.yml
│       ├── sa_b200_gnb
│       │   └── docker-compose.yml
│       ├── sa_b200_jetson_nrue
│       │   └── docker-compose.yml
│       ├── sa_e1_b200_gnb
│       │   └── docker-compose.yml
│       ├── sa_f1_b200_gnb
│       │   └── docker-compose.yml
│       ├── sa_fhi_7.2_benetel550_2x2_100MHz_9b_mplane_gnb
│       │   ├── docker-compose.yml
│       │   ├── setup_cleanup.sh
│       │   ├── setup_config.sh
│       │   └── setup_sriov_benetel.sh
│       ├── sa_fhi_7.2_benetel550_4x4_40MHz_9b_mplane_gnb
│       │   ├── docker-compose.yml
│       │   ├── setup_cleanup.sh
│       │   ├── setup_config.sh
│       │   └── setup_sriov_benetel.sh
│       ├── sa_fhi_7.2_benetel_4x4_du
│       │   ├── docker-compose.yml
│       │   └── setup_sriov_benetel.sh
│       ├── sa_fhi_7.2_benetel_8x8_du
│       │   ├── docker-compose.yml
│       │   └── setup_sriov_benetel650_650.sh
│       ├── sa_fhi_7.2_liteon_4x4_gnb
│       │   ├── docker-compose.yml
│       │   └── setup_sriov_liteon.sh
│       ├── sa_fhi_7.2_metanoia_4x4_gnb
│       │   ├── docker-compose.yml
│       │   └── setup_sriov_metanoia.sh
│       ├── sa_fhi_7.2_vvdn_4x4_du
│       │   ├── docker-compose.yml
│       │   └── setup_sriov_vvdn.sh
│       ├── sa_fhi_7.2_vvdn_4x4_monolithic_gnb
│       │   ├── docker-compose.yml
│       │   └── setup_sriov_vvdn.sh
│       ├── sa_fhi_7.2_vvdn_4x4_nfapi
│       │   ├── docker-compose.yml
│       │   └── setup_sriov_vvdn.sh
│       ├── sa_fhi_7.2_vvdn_gnb
│       │   ├── README.md
│       │   ├── docker-compose.yml
│       │   ├── setup_config.sh
│       │   └── setup_sriov_vvdn.sh
│       ├── sa_gnb_aerial
│       │   ├── aerial_l1_entrypoint.sh
│       │   ├── cuphycontroller_P5G_WNC_GH.yaml
│       │   ├── docker-compose-ue.yaml
│       │   └── docker-compose.yaml
│       ├── sa_gnb_aerial_30MHz
│       │   ├── aerial_l1_entrypoint.sh
│       │   ├── cuphycontroller_P5G_WNC_GH.yaml
│       │   └── docker-compose.yaml
│       ├── sa_gnb_aerial_ul
│       │   ├── aerial_l1_entrypoint.sh
│       │   ├── cuphycontroller_P5G_WNC_GH_ul.yaml
│       │   └── docker-compose.yaml
│       └── sa_sc_b200_gnb
│           └── docker-compose.yml
├── cmake_targets
│   ├── CPM.cmake
│   ├── at_commands
│   │   └── CMakeLists.txt
│   ├── build_oai
│   ├── cross-arm.cmake
│   ├── macros.cmake
│   └── tools
│       ├── MODULES
│       │   ├── FindGnuTLS.cmake
│       │   ├── Findarmral.cmake
│       │   ├── Findsctp.cmake
│       │   └── Findxran.cmake
│       ├── build_helper
│       ├── install_libraries_to_system.patch
│       ├── install_wls_lib.patch
│       ├── oran_fhi_integration_patches
│       │   └── F
│       │       └── oaioran_F.patch
│       ├── test_helper
│       ├── uhd-3.15-tdd-patch.diff
│       ├── uhd-4.5plus-tdd-patch.diff
│       └── uhd-4.x-tdd-patch.diff
├── common
│   ├── 5g_platform_types.h
│   ├── CMakeLists.txt
│   ├── cmake_defs.h.in
│   ├── config
│   │   ├── DOC
│   │   │   ├── config
│   │   │   │   ├── arch.md
│   │   │   │   ├── devusage
│   │   │   │   │   ├── addaparam.md
│   │   │   │   │   ├── addparamset.md
│   │   │   │   │   ├── api.md
│   │   │   │   │   └── struct.md
│   │   │   │   ├── devusage.md
│   │   │   │   └── rtusage.md
│   │   │   └── config.md
│   │   ├── config_cmdline.c
│   │   ├── config_common.c
│   │   ├── config_common.h
│   │   ├── config_load_configmodule.c
│   │   ├── config_load_configmodule.h
│   │   ├── config_paramdesc.h
│   │   ├── config_userapi.c
│   │   ├── config_userapi.h
│   │   ├── libconfig
│   │   │   ├── config_libconfig.c
│   │   │   ├── config_libconfig.h
│   │   │   └── config_libconfig_private.h
│   │   ├── tests
│   │   │   ├── CMakeLists.txt
│   │   │   ├── test_config.conf
│   │   │   └── test_config_cmdline.cpp
│   │   └── yaml
│   │       ├── CMakeLists.txt
│   │       ├── config_yaml.cpp
│   │       └── tests
│   │           ├── CMakeLists.txt
│   │           ├── malformed.yaml
│   │           ├── test1.yaml
│   │           ├── test_int_array.yaml
│   │           ├── test_ipv4.yaml
│   │           ├── test_list.yaml
│   │           ├── test_list_of_mappings.yml
│   │           ├── test_read_mapping_as_list.yaml
│   │           ├── test_read_str_as_int.yaml
│   │           ├── test_recursion.yaml
│   │           ├── test_string.yaml
│   │           └── test_yaml_config.cpp
│   ├── instrumentation.h
│   ├── ngran_types.h
│   ├── oai_version.h.in
│   ├── openairinterface5g_limits.h
│   ├── platform_constants.h
│   ├── platform_types.h
│   ├── ran_context.h
│   └── utils
│       ├── CMakeLists.txt
│       ├── DOC
│       │   ├── loader
│       │   │   ├── arch.md
│       │   │   ├── devusage
│       │   │   │   ├── api.md
│       │   │   │   ├── loading.md
│       │   │   │   └── struct.md
│       │   │   ├── devusage.md
│       │   │   └── rtusage.md
│       │   └── loader.md
│       ├── LOG
│       │   ├── CMakeLists.txt
│       │   ├── DOC
│       │   │   ├── addconsoletrace.md
│       │   │   ├── arch.md
│       │   │   ├── configurelog.md
│       │   │   ├── devusage.md
│       │   │   ├── log.md
│       │   │   ├── lttng_logs.md
│       │   │   └── rtusage.md
│       │   ├── README.txt
│       │   ├── log.c
│       │   ├── log.h
│       │   ├── lttng-log.h
│       │   ├── lttng-tp.c
│       │   ├── lttng-tp.h
│       │   ├── vcd_signal_dumper.c
│       │   └── vcd_signal_dumper.h
│       ├── T
│       │   ├── CMakeLists.txt
│       │   ├── DOC
│       │   │   ├── T
│       │   │   │   ├── basic.md
│       │   │   │   ├── csv.md
│       │   │   │   ├── enb.md
│       │   │   │   ├── enb_trace.odp
│       │   │   │   ├── enb_trace.png
│       │   │   │   ├── example.raw
│       │   │   │   ├── howto_new_trace.md
│       │   │   │   ├── howto_new_trace.patch
│       │   │   │   ├── multi.md
│       │   │   │   ├── record.md
│       │   │   │   ├── record_db.md
│       │   │   │   ├── replay.md
│       │   │   │   ├── to_vcd.md
│       │   │   │   ├── wireshark.md
│       │   │   │   └── wireshark.png
│       │   │   └── T.md
│       │   ├── Makefile
│       │   ├── README
│       │   ├── T.c
│       │   ├── T.h
│       │   ├── T_defs.h
│       │   ├── T_messages.txt
│       │   ├── T_messages_creator.c
│       │   ├── T_messages_creator.h
│       │   ├── check_vcd.c
│       │   ├── defs.h
│       │   ├── generate_Txx.c
│       │   ├── genids.c
│       │   ├── local_tracer.c
│       │   ├── plot.c
│       │   ├── tracee
│       │   │   ├── Makefile
│       │   │   ├── README
│       │   │   ├── common
│       │   │   │   └── config
│       │   │   │       └── config_userapi.h
│       │   │   └── tracee.c
│       │   └── tracer
│       │       ├── CMakeLists.txt
│       │       ├── Makefile
│       │       ├── configuration.c
│       │       ├── configuration.h
│       │       ├── csv.c
│       │       ├── database.c
│       │       ├── database.h
│       │       ├── defs.h
│       │       ├── enb.c
│       │       ├── event.c
│       │       ├── event.h
│       │       ├── event_selector.c
│       │       ├── event_selector.h
│       │       ├── extract.c
│       │       ├── extract_config.c
│       │       ├── extract_input_subframe.c
│       │       ├── extract_output_subframe.c
│       │       ├── extract_prs_dumps.sh
│       │       ├── filter
│       │       │   ├── CMakeLists.txt
│       │       │   ├── Makefile
│       │       │   ├── filter.c
│       │       │   └── filter.h
│       │       ├── gnb.c
│       │       ├── gnb_mac.c
│       │       ├── gui
│       │       │   ├── CMakeLists.txt
│       │       │   ├── Makefile
│       │       │   ├── container.c
│       │       │   ├── event.c
│       │       │   ├── gui.c
│       │       │   ├── gui.h
│       │       │   ├── gui_defs.h
│       │       │   ├── image.c
│       │       │   ├── init.c
│       │       │   ├── label.c
│       │       │   ├── loop.c
│       │       │   ├── notify.c
│       │       │   ├── positioner.c
│       │       │   ├── space.c
│       │       │   ├── test.c
│       │       │   ├── textarea.c
│       │       │   ├── textlist.c
│       │       │   ├── timeline.c
│       │       │   ├── toplevel_window.c
│       │       │   ├── widget.c
│       │       │   ├── x.c
│       │       │   ├── x.h
│       │       │   ├── x_defs.h
│       │       │   └── xy_plot.c
│       │       ├── gui.c
│       │       ├── hacks
│       │       │   ├── Makefile
│       │       │   ├── ant0.c
│       │       │   ├── dump_nack_signal.c
│       │       │   ├── multi-rru-clean.c
│       │       │   ├── pilot_timeplot.sh
│       │       │   ├── plot-ofdm.c
│       │       │   ├── time_meas.c
│       │       │   └── timeplot.c
│       │       ├── handler.c
│       │       ├── handler.h
│       │       ├── logger
│       │       │   ├── CMakeLists.txt
│       │       │   ├── Makefile
│       │       │   ├── framelog.c
│       │       │   ├── iqdotlog.c
│       │       │   ├── iqlog.c
│       │       │   ├── logger.c
│       │       │   ├── logger.h
│       │       │   ├── logger_defs.h
│       │       │   ├── textlog.c
│       │       │   ├── throughputlog.c
│       │       │   ├── ticked_ttilog.c
│       │       │   ├── ticklog.c
│       │       │   ├── timelog.c
│       │       │   └── ttilog.c
│       │       ├── macpdu2wireshark.c
│       │       ├── multi.c
│       │       ├── openair_logo.h
│       │       ├── openair_logo.png
│       │       ├── packet-mac-lte.h
│       │       ├── plot.c
│       │       ├── record.c
│       │       ├── record_db.cpp
│       │       ├── replay.c
│       │       ├── shared_memory_config.h
│       │       ├── t_tracer_app_gnb.c
│       │       ├── t_tracer_app_ue.c
│       │       ├── textlog.c
│       │       ├── to_vcd.c
│       │       ├── ue.c
│       │       ├── utils.c
│       │       ├── utils.h
│       │       ├── vcd.c
│       │       └── view
│       │           ├── CMakeLists.txt
│       │           ├── Makefile
│       │           ├── scrolltti.c
│       │           ├── stdout.c
│       │           ├── textlist.c
│       │           ├── ticktime.c
│       │           ├── time.c
│       │           ├── tti.c
│       │           ├── view.h
│       │           └── xy.c
│       ├── actor
│       │   ├── CMakeLists.txt
│       │   ├── README.md
│       │   ├── actor.c
│       │   ├── actor.h
│       │   └── tests
│       │       ├── CMakeLists.txt
│       │       └── test_actor.cpp
│       ├── alg
│       │   ├── CMakeLists.txt
│       │   ├── find.c
│       │   ├── find.h
│       │   ├── foreach.c
│       │   └── foreach.h
│       ├── assertions.h
│       ├── barrier
│       │   ├── CMakeLists.txt
│       │   ├── barrier.c
│       │   ├── barrier.h
│       │   └── tests
│       │       ├── CMakeLists.txt
│       │       └── test_barrier.cpp
│       ├── bits.c
│       ├── bits.h
│       ├── collection
│       │   ├── linear_alloc.h
│       │   ├── queue.h
│       │   └── tree.h
│       ├── config.h
│       ├── data_recording
│       │   ├── config
│       │   │   ├── config_data_recording.json
│       │   │   └── wireless_link_parameter_map.yaml
│       │   ├── data_recording_app_v1.1.py
│       │   ├── lib
│       │   │   ├── __init__.py
│       │   │   ├── common_utils.py
│       │   │   ├── config_interface.py
│       │   │   ├── data_recording_messages_def.py
│       │   │   ├── shared_memory_interface.py
│       │   │   ├── sigmf_interface.py
│       │   │   ├── sync_service.py
│       │   │   └── wireless_parameters_mapper.py
│       │   ├── requirements.txt
│       │   └── sync_validation_demo.py
│       ├── ds
│       │   ├── CMakeLists.txt
│       │   ├── byte_array.c
│       │   ├── byte_array.h
│       │   ├── byte_array_producer.c
│       │   ├── byte_array_producer.h
│       │   ├── hashtable.c
│       │   ├── hashtable.h
│       │   ├── obj_hashtable.c
│       │   ├── obj_hashtable.h
│       │   ├── seq_arr.c
│       │   ├── seq_arr.h
│       │   ├── spsc_q.c
│       │   ├── spsc_q.h
│       │   └── tests
│       │       ├── CMakeLists.txt
│       │       ├── test_hashtable.cpp
│       │       ├── test_seq_array.c
│       │       ├── test_spsc_q.cpp
│       │       └── test_spsc_q_perf.cpp
│       ├── eq_check.h
│       ├── fsn.c
│       ├── fsn.h
│       ├── load_module_shlib.c
│       ├── load_module_shlib.h
│       ├── lte
│       │   ├── prach_utils.c
│       │   ├── prach_utils.h
│       │   └── ue_power.c
│       ├── mem
│       │   ├── memory.c
│       │   └── oai_memory.h
│       ├── minimal_stub.c
│       ├── nr
│       │   ├── CMakeLists.txt
│       │   ├── nr_common.c
│       │   ├── nr_common.h
│       │   └── tests
│       │       ├── CMakeLists.txt
│       │       └── test_nr_common.cpp
│       ├── oai_asn1.h
│       ├── ocp_itti
│       │   ├── all_msg.h
│       │   ├── intertask_interface.cpp
│       │   ├── intertask_interface.h
│       │   └── itti.md
│       ├── shm_iq_channel
│       │   ├── CMakeLists.txt
│       │   ├── shm_td_iq_channel.c
│       │   ├── shm_td_iq_channel.h
│       │   └── tests
│       │       ├── CMakeLists.txt
│       │       └── test_shm_td_iq_channel.c
│       ├── simple_executable.h
│       ├── system.c
│       ├── system.h
│       ├── telnetsrv
│       │   ├── CMakeLists.txt
│       │   ├── DOC
│       │   │   ├── telnetaddcmd.md
│       │   │   ├── telnetarch.md
│       │   │   ├── telnetgetset.md
│       │   │   ├── telnethelp.md
│       │   │   ├── telnethist.md
│       │   │   ├── telnetloader.md
│       │   │   ├── telnetlog.md
│       │   │   ├── telnetloop.md
│       │   │   ├── telnetmeasur.md
│       │   │   ├── telneto1.md
│       │   │   ├── telnetsrv.md
│       │   │   └── telnetusage.md
│       │   ├── telnetsrv.c
│       │   ├── telnetsrv.h
│       │   ├── telnetsrv_5Gue_measurements.c
│       │   ├── telnetsrv_bearer.c
│       │   ├── telnetsrv_ci.c
│       │   ├── telnetsrv_ciUE.c
│       │   ├── telnetsrv_cpumeasur_def.h
│       │   ├── telnetsrv_enb_measurements.c
│       │   ├── telnetsrv_enb_phycmd.c
│       │   ├── telnetsrv_loader.c
│       │   ├── telnetsrv_loader.h
│       │   ├── telnetsrv_ltemeasur_def.h
│       │   ├── telnetsrv_measurements.c
│       │   ├── telnetsrv_measurements.h
│       │   ├── telnetsrv_o1.c
│       │   ├── telnetsrv_phycmd.h
│       │   ├── telnetsrv_proccmd.c
│       │   ├── telnetsrv_proccmd.h
│       │   └── telnetsrv_rrc.c
│       ├── tests
│       │   ├── CMakeLists.txt
│       │   ├── test_fsn.cpp
│       │   └── test_tpool_vs_actors.c
│       ├── threadPool
│       │   ├── CMakeLists.txt
│       │   ├── bounded_notified_fifo.h
│       │   ├── measurement_display.c
│       │   ├── notified_fifo.h
│       │   ├── pthread_utils.h
│       │   ├── task.h
│       │   ├── task_ans.c
│       │   ├── task_ans.h
│       │   ├── test
│       │   │   ├── CMakeLists.txt
│       │   │   └── test_thread-pool.c
│       │   ├── thread-pool.c
│       │   ├── thread-pool.h
│       │   └── thread-pool.md
│       ├── time_manager
│       │   ├── CMakeLists.txt
│       │   ├── tests
│       │   │   ├── CMakeLists.txt
│       │   │   ├── test_auto.c
│       │   │   └── test_manual.c
│       │   ├── time_client.c
│       │   ├── time_client.h
│       │   ├── time_manager.c
│       │   ├── time_manager.h
│       │   ├── time_server.c
│       │   ├── time_server.h
│       │   ├── time_source.c
│       │   └── time_source.h
│       ├── time_meas.c
│       ├── time_meas.h
│       ├── time_stat.c
│       ├── time_stat.h
│       ├── tuntap_if.c
│       ├── tuntap_if.h
│       ├── utils.c
│       ├── utils.h
│       ├── var_array.h
│       └── websrv
│           ├── CMakeLists.txt
│           ├── DOC
│           │   ├── logscfg.png
│           │   ├── main.png
│           │   ├── scope.png
│           │   ├── websrv.md
│           │   ├── websrvarch.md
│           │   ├── websrvdev.md
│           │   └── websrvuse.md
│           ├── frontend
│           │   ├── README.md
│           │   ├── angular.json
│           │   ├── e2e
│           │   │   ├── protractor-ci.conf.js
│           │   │   ├── protractor.conf.js
│           │   │   ├── src
│           │   │   │   ├── app.e2e-spec.ts
│           │   │   │   └── app.po.ts
│           │   │   └── tsconfig.json
│           │   ├── package-lock.json
│           │   ├── package.json
│           │   ├── src
│           │   │   ├── app
│           │   │   │   ├── api
│           │   │   │   │   ├── commands.api.ts
│           │   │   │   │   ├── help.api.ts
│           │   │   │   │   ├── info.api.ts
│           │   │   │   │   └── scope.api.ts
│           │   │   │   ├── app-routing.module.ts
│           │   │   │   ├── app.component.css
│           │   │   │   ├── app.component.html
│           │   │   │   ├── app.component.ts
│           │   │   │   ├── app.module.ts
│           │   │   │   ├── components
│           │   │   │   │   ├── commands
│           │   │   │   │   │   ├── commands.component.html
│           │   │   │   │   │   ├── commands.component.scss
│           │   │   │   │   │   └── commands.component.ts
│           │   │   │   │   ├── confirm
│           │   │   │   │   │   ├── confirm.component.css
│           │   │   │   │   │   ├── confirm.component.html
│           │   │   │   │   │   └── confirm.component.ts
│           │   │   │   │   ├── dialog
│           │   │   │   │   │   ├── dialog.component.css
│           │   │   │   │   │   ├── dialog.component.html
│           │   │   │   │   │   └── dialog.component.ts
│           │   │   │   │   ├── info
│           │   │   │   │   │   ├── info.component.html
│           │   │   │   │   │   ├── info.component.scss
│           │   │   │   │   │   └── info.component.ts
│           │   │   │   │   ├── question
│           │   │   │   │   │   ├── question.component.css
│           │   │   │   │   │   ├── question.component.html
│           │   │   │   │   │   └── question.component.ts
│           │   │   │   │   └── scope
│           │   │   │   │       ├── scope.component.css
│           │   │   │   │       ├── scope.component.html
│           │   │   │   │       └── scope.component.ts
│           │   │   │   ├── controls
│           │   │   │   │   ├── cmd.control.ts
│           │   │   │   │   ├── info.control.ts
│           │   │   │   │   ├── module.control.ts
│           │   │   │   │   ├── param.control.ts
│           │   │   │   │   ├── row.control.ts
│           │   │   │   │   └── var.control.ts
│           │   │   │   ├── interceptors
│           │   │   │   │   ├── error.interceptor.ts
│           │   │   │   │   ├── interceptors.ts
│           │   │   │   │   └── spinner.interceptor.ts
│           │   │   │   └── services
│           │   │   │       ├── dialog.service.ts
│           │   │   │       ├── download.service.ts
│           │   │   │       ├── loading.service.ts
│           │   │   │       └── websocket.service.ts
│           │   │   ├── assets
│           │   │   ├── commondefs.ts
│           │   │   ├── environments
│           │   │   │   ├── environment.prod.ts
│           │   │   │   └── environment.ts
│           │   │   ├── favicon.ico
│           │   │   ├── index.html
│           │   │   ├── main.ts
│           │   │   ├── polyfills.ts
│           │   │   ├── styles.css
│           │   │   └── test.ts
│           │   ├── tsconfig.app.json
│           │   ├── tsconfig.json
│           │   └── tsconfig.spec.json
│           ├── helpfiles
│           │   ├── cmd_channelmod_show_channelid.html
│           │   ├── cmd_channelmod_show_current.html
│           │   ├── cmd_channelmod_show_predef.html
│           │   ├── question_setdistance_input.html
│           │   ├── question_show_channelid_input.html
│           │   ├── rfsimu_show_models_algorithm.html
│           │   ├── rfsimu_show_models_model_index.html
│           │   ├── rfsimu_show_models_model_name.html
│           │   ├── rfsimu_show_models_module_owner.html
│           │   ├── scope_control_dataack.html
│           │   ├── softmodem_show_threadsched_nice.html
│           │   ├── softmodem_show_threadsched_oai_priority.html
│           │   ├── softmodem_show_threadsched_priority.html
│           │   └── softmodem_show_threadsched_sched_policy.html
│           ├── websrv.c
│           ├── websrv.h
│           ├── websrv_noforms.c
│           ├── websrv_noforms.h
│           ├── websrv_scope.c
│           ├── websrv_utils.c
│           └── websrv_websockets.c
├── doc
│   ├── 5Gnas.md
│   ├── Aerial_FAPI_Split_Tutorial.md
│   ├── BUILD.md
│   ├── CMakeLists.txt
│   ├── Doxyfile
│   ├── E1AP
│   │   ├── E1-design.md
│   │   ├── e1ap_procedures.md
│   │   └── images
│   │       ├── e1-archi.pdf
│   │       ├── e1-archi.png
│   │       └── e1-archi.tex
│   ├── F1AP
│   │   ├── F1-design.md
│   │   └── F1AP-lib.md
│   ├── FEATURE_SET.md
│   ├── GET_SOURCES.md
│   ├── L1SIM.md
│   ├── L2NFAPI.md
│   ├── L2NFAPI_NOS1.md
│   ├── L2NFAPI_S1.md
│   ├── LDPC_OFFLOAD_SETUP.md
│   ├── MAC
│   │   ├── TDD_Frame_Structure.png
│   │   ├── mac-usage.md
│   │   └── scheduler-architecture.md
│   ├── NR_NFAPI_archi.md
│   ├── NR_SA_Tutorial_COTS_UE.md
│   ├── NR_SA_Tutorial_OAI_CN5G.md
│   ├── NR_SA_Tutorial_OAI_multi_UE.md
│   ├── NR_SA_Tutorial_OAI_nrUE.md
│   ├── ORAN_FHI7.2_Tutorial.md
│   ├── README.md
│   ├── RRC
│   │   ├── ho.mmd
│   │   ├── ho.png
│   │   ├── rrc-dev.md
│   │   └── rrc-usage.md
│   ├── RUNMODEM.md
│   ├── RUN_NR_PRS.md
│   ├── SW-archi-graph.md
│   ├── SW_archi.md
│   ├── Supported_Hardware_Operating_System.md
│   ├── TESTBenches.md
│   ├── TESTING_OAI_NSA_COTS_UE.md
│   ├── UL_MIMO.md
│   ├── UnitTests.md
│   ├── analog_beamforming.md
│   ├── clang-format.md
│   ├── code-style-contrib.md
│   ├── cross-compile.md
│   ├── d2d_emulator_setup.md
│   ├── data_recording.md
│   ├── dev_tools
│   │   ├── sanitizers.md
│   │   └── tracy.md
│   ├── doc_best_practices.md
│   ├── environment-variables.md
│   ├── episys
│   │   ├── Channel_Abstraction_UE_Handling_LTE.PNG
│   │   ├── Proxy_Interface_Diagram.PNG
│   │   ├── functional_diagram_proxy_lte.png
│   │   ├── functional_diagram_proxy_nsa.png
│   │   ├── lte_mode_l2_emulator
│   │   │   └── README.md
│   │   └── nsa_mode_l2_emulator
│   │       └── README.md
│   ├── gNB_frequency_setup.md
│   ├── handover-tutorial.md
│   ├── images
│   │   ├── L2-sim-S1-3-host-deployment.png
│   │   ├── L2-sim-noS1-2-host-deployment.png
│   │   ├── L2-sim-single-server-deployment.png
│   │   ├── PRS_CFR_FR2_64PRB_8rsc.PNG
│   │   ├── PRS_CIR_FR2_64PRB_8rsc.PNG
│   │   ├── USRP_tune_offset.png
│   │   ├── attach_signaling_scheme.jpg
│   │   ├── data_recording_arch.svg
│   │   ├── data_serialization_tx_scrambled_bit_message.svg
│   │   ├── docker-deploy-oai-7-2.drawio.xml
│   │   ├── docker-deploy-oai-7-2.png
│   │   ├── mimo_antenna_ports.png
│   │   ├── nr-ue-threads.svg
│   │   ├── oai_enb_block_diagram.png
│   │   ├── oai_enb_func_split_arch.png
│   │   ├── oai_final_logo.png
│   │   ├── oai_fr1_lab.jpg
│   │   ├── oai_fr1_setup.jpg
│   │   ├── oai_logo.png
│   │   ├── oai_lte_enb_func_split_arch.png
│   │   └── sigmf_dataset.svg
│   ├── iqrecordplayer_usage.md
│   ├── nfapi.md
│   ├── nr-ue-design.md
│   ├── ntn-configuration.md
│   ├── openair_header.tex
│   ├── packages.md
│   ├── physical-simulators.md
│   ├── rach_processing_in_gNB.md
│   ├── runmodem-nrue.md
│   ├── system_requirements.md
│   ├── testbenches_doc_resources
│   │   ├── 4g-faraday-bench.pdf
│   │   ├── 4g-faraday-bench.png
│   │   ├── 4g-faraday-bench.tex
│   │   ├── 5g-aw2s-bench.pdf
│   │   ├── 5g-aw2s-bench.png
│   │   ├── 5g-aw2s-bench.tex
│   │   ├── 5g-nrue-bench.pdf
│   │   ├── 5g-nrue-bench.png
│   │   ├── 5g-nrue-bench.tex
│   │   ├── 5g-nsa-faraday-bench.pdf
│   │   ├── 5g-nsa-faraday-bench.png
│   │   ├── 5g-nsa-faraday-bench.tex
│   │   ├── 5g-ota-bench.pdf
│   │   ├── 5g-ota-bench.png
│   │   ├── 5g-ota-bench.tex
│   │   ├── amariue.png
│   │   ├── antenna.pdf
│   │   ├── aw2s.png
│   │   ├── b200-mini.png
│   │   ├── b210.jpg
│   │   ├── benches.vsdx
│   │   ├── n310.png
│   │   ├── openshift.png
│   │   ├── phone.pdf
│   │   ├── quectel.png
│   │   ├── server.pdf
│   │   └── x310.jpg
│   ├── testing_oai_nsa_w_cots_ue_resources
│   │   ├── enb.conf
│   │   ├── gnb.conf
│   │   ├── oai_enb.log
│   │   ├── oai_fr1_setup.vsdx
│   │   └── oai_gnb.log
│   ├── time_management.md
│   ├── tuning_and_security.md
│   └── tutorial_resources
│       ├── oai-cn5g
│       │   ├── conf
│       │   │   ├── config.yaml
│       │   │   ├── sip.conf
│       │   │   └── users.conf
│       │   ├── database
│       │   │   └── oai_db.sql
│       │   ├── docker-compose-positioning.yaml
│       │   ├── docker-compose.yaml
│       │   └── healthscripts
│       │       └── mysql-healthcheck.sh
│       └── positioning
│           └── InputData.json
├── docker
│   ├── Dockerfile.base.rhel9
│   ├── Dockerfile.base.rocky
│   ├── Dockerfile.base.ubuntu
│   ├── Dockerfile.base.ubuntu.cross-arm64
│   ├── Dockerfile.build.fhi72.native_arm.ubuntu
│   ├── Dockerfile.build.fhi72.rhel9
│   ├── Dockerfile.build.fhi72.t2.ubuntu
│   ├── Dockerfile.build.fhi72.ubuntu
│   ├── Dockerfile.build.rhel9
│   ├── Dockerfile.build.rocky
│   ├── Dockerfile.build.ubuntu
│   ├── Dockerfile.build.ubuntu.cross-arm64
│   ├── Dockerfile.clang.rhel9
│   ├── Dockerfile.eNB.rhel9
│   ├── Dockerfile.eNB.rocky
│   ├── Dockerfile.eNB.ubuntu
│   ├── Dockerfile.gNB.aerial.ubuntu
│   ├── Dockerfile.gNB.aerial.ubuntu.sanitize-address
│   ├── Dockerfile.gNB.aw2s.rhel9
│   ├── Dockerfile.gNB.aw2s.rocky
│   ├── Dockerfile.gNB.aw2s.ubuntu
│   ├── Dockerfile.gNB.fhi72.rhel9
│   ├── Dockerfile.gNB.fhi72.rocky
│   ├── Dockerfile.gNB.fhi72.t2.ubuntu
│   ├── Dockerfile.gNB.fhi72.ubuntu
│   ├── Dockerfile.gNB.rhel9
│   ├── Dockerfile.gNB.rocky
│   ├── Dockerfile.gNB.ubuntu
│   ├── Dockerfile.lteRU.rhel9
│   ├── Dockerfile.lteRU.ubuntu
│   ├── Dockerfile.lteUE.rhel9
│   ├── Dockerfile.lteUE.rocky
│   ├── Dockerfile.lteUE.ubuntu
│   ├── Dockerfile.nr-cuup.rhel9
│   ├── Dockerfile.nr-cuup.rocky
│   ├── Dockerfile.nr-cuup.ubuntu
│   ├── Dockerfile.nrORU.fhi72.ubuntu
│   ├── Dockerfile.nrUE.rhel9
│   ├── Dockerfile.nrUE.rocky
│   ├── Dockerfile.nrUE.ubuntu
│   ├── Dockerfile.phySim.rhel9
│   ├── README.md
│   ├── debug_core_image.sh
│   └── scripts
│       ├── check-prach-io.sh
│       ├── enb_entrypoint.sh
│       ├── gnb-aw2s_entrypoint.sh
│       ├── gnb_entrypoint.sh
│       ├── lte_ru_entrypoint.sh
│       ├── lte_ue_entrypoint.sh
│       ├── nr_oru_entrypoint.sh
│       └── nr_ue_entrypoint.sh
├── executables
│   ├── CMakeLists.txt
│   ├── create_tasks.c
│   ├── create_tasks.h
│   ├── create_tasks_mbms.c
│   ├── create_tasks_ue.c
│   ├── lte-enb.c
│   ├── lte-ru.c
│   ├── lte-softmodem.c
│   ├── lte-softmodem.h
│   ├── lte-ue.c
│   ├── lte-uesoftmodem.c
│   ├── main_nr_ru.c
│   ├── main_ru.c
│   ├── nr-cuup.c
│   ├── nr-gnb.c
│   ├── nr-ru.c
│   ├── nr-softmodem-common.h
│   ├── nr-softmodem.c
│   ├── nr-softmodem.h
│   ├── nr-ue-ru.c
│   ├── nr-ue-ru.h
│   ├── nr-ue.c
│   ├── nr-uesoftmodem.c
│   ├── nr-uesoftmodem.h
│   ├── position_interface.c
│   ├── position_interface.h
│   ├── ru_control.c
│   ├── softmodem-common.c
│   ├── softmodem-common.h
│   ├── stats.c
│   ├── stats.h
│   ├── thread-common.h
│   └── uecap.raw
├── fronthaul
│   ├── CMakeLists.txt
│   ├── README.md
│   ├── core
│   │   ├── CMakeLists.txt
│   │   ├── README.md
│   │   ├── fh_recv.c
│   │   ├── fh_recv.h
│   │   ├── fh_send.c
│   │   ├── fh_send.h
│   │   ├── fh_timer.c
│   │   ├── fh_timer.h
│   │   └── tests
│   │       ├── CMakeLists.txt
│   │       ├── test_fh_recv.c
│   │       ├── test_fh_recv_drift.c
│   │       ├── test_fh_send.c
│   │       ├── test_fh_timer.c
│   │       └── test_fh_timer_drift.c
│   ├── oru
│   │   ├── CMakeLists.txt
│   │   ├── oru_fh.c
│   │   ├── oru_fh.h
│   │   ├── oru_io.c
│   │   ├── oru_io.h
│   │   ├── oru_packet_processor.c
│   │   ├── oru_packet_processor.h
│   │   └── tests
│   │       ├── CMakeLists.txt
│   │       ├── run_oru_pcap_test.sh
│   │       ├── test_oru_fh.c
│   │       ├── test_oru_io.c
│   │       ├── test_oru_packet_processor.c
│   │       └── test_oru_pcap.c
│   └── xran_pkt
│       ├── CMakeLists.txt
│       ├── tests
│       │   ├── CMakeLists.txt
│       │   ├── test_xran_pkt.c
│       │   └── xran_pcap_dump.c
│       ├── xran_pkt.h
│       ├── xran_pkt_api.c
│       ├── xran_pkt_api.h
│       ├── xran_pkt_cp.h
│       └── xran_pkt_up.h
├── maketags
├── nfapi
│   ├── CHANGES.md
│   ├── CMakeLists.txt
│   ├── README
│   ├── oai_integration
│   │   ├── CMakeLists.txt
│   │   ├── aerial
│   │   │   ├── CMakeLists.txt
│   │   │   ├── fapi_nvIPC.c
│   │   │   ├── fapi_nvIPC.h
│   │   │   ├── fapi_vnf_p7.c
│   │   │   └── fapi_vnf_p7.h
│   │   ├── gnb_ind_vars.c
│   │   ├── gnb_ind_vars.h
│   │   ├── nfapi.c
│   │   ├── nfapi_pnf.c
│   │   ├── nfapi_pnf.h
│   │   ├── nfapi_vnf.c
│   │   ├── nfapi_vnf.h
│   │   ├── socket
│   │   │   ├── CMakeLists.txt
│   │   │   ├── include
│   │   │   │   ├── socket_common.h
│   │   │   │   ├── socket_pnf.h
│   │   │   │   └── socket_vnf.h
│   │   │   ├── socket_common.c
│   │   │   ├── socket_pnf.c
│   │   │   └── socket_vnf.c
│   │   ├── vendor_ext.h
│   │   └── wls_integration
│   │       ├── CMakeLists.txt
│   │       ├── include
│   │       │   ├── wls_common.h
│   │       │   ├── wls_pnf.h
│   │       │   └── wls_vnf.h
│   │       ├── wls_common.c
│   │       ├── wls_pnf.c
│   │       └── wls_vnf.c
│   ├── open-nFAPI
│   │   ├── CHANGELOG.md
│   │   ├── CMakeLists.txt
│   │   ├── LICENSE.md
│   │   ├── Makefile.am
│   │   ├── README.md
│   │   ├── common
│   │   │   ├── CMakeLists.txt
│   │   │   ├── Makefile.am
│   │   │   ├── public_inc
│   │   │   │   ├── debug.h
│   │   │   │   └── nfapi.h
│   │   │   └── src
│   │   │       ├── debug.c
│   │   │       └── nfapi.c
│   │   ├── configure.ac
│   │   ├── docs
│   │   │   ├── Doxyfile
│   │   │   ├── Doxyfile.in
│   │   │   ├── Makefile.am
│   │   │   └── doxygen.h
│   │   ├── fapi
│   │   │   ├── CMakeLists.txt
│   │   │   ├── inc
│   │   │   │   ├── nr_fapi.h
│   │   │   │   ├── nr_fapi_p5.h
│   │   │   │   ├── nr_fapi_p5_utils.h
│   │   │   │   ├── nr_fapi_p7.h
│   │   │   │   └── nr_fapi_p7_utils.h
│   │   │   └── src
│   │   │       ├── nr_fapi.c
│   │   │       ├── nr_fapi_p5.c
│   │   │       ├── nr_fapi_p5_utils.c
│   │   │       ├── nr_fapi_p7.c
│   │   │       └── nr_fapi_p7_utils.c
│   │   ├── integration_tests
│   │   │   ├── Makefile.am
│   │   │   └── main.cpp
│   │   ├── nfapi
│   │   │   ├── CMakeLists.txt
│   │   │   ├── Makefile.am
│   │   │   ├── public_inc
│   │   │   │   ├── fapi_nr_ue_constants.h
│   │   │   │   ├── fapi_nr_ue_interface.h
│   │   │   │   ├── nfapi_common_interface.h
│   │   │   │   ├── nfapi_interface.h
│   │   │   │   ├── nfapi_nr_interface.h
│   │   │   │   ├── nfapi_nr_interface_scf.h
│   │   │   │   ├── nr_nfapi_p7.h
│   │   │   │   └── sidelink_nr_ue_interface.h
│   │   │   ├── src
│   │   │   │   ├── nfapi_lte_p5.c
│   │   │   │   ├── nfapi_lte_p7.c
│   │   │   │   ├── nfapi_nr_p5.c
│   │   │   │   ├── nfapi_nr_p7.c
│   │   │   │   └── nfapi_p4.c
│   │   │   └── tests
│   │   │       ├── Makefile.am
│   │   │       └── nfapi_cunit_main.c
│   │   ├── pnf
│   │   │   ├── CMakeLists.txt
│   │   │   ├── Makefile.am
│   │   │   ├── inc
│   │   │   │   ├── pnf.h
│   │   │   │   └── pnf_p7.h
│   │   │   ├── public_inc
│   │   │   │   └── nfapi_pnf_interface.h
│   │   │   ├── src
│   │   │   │   ├── pnf.c
│   │   │   │   ├── pnf_interface.c
│   │   │   │   ├── pnf_p7.c
│   │   │   │   └── pnf_p7_interface.c
│   │   │   └── tests
│   │   │       ├── Makefile.am
│   │   │       └── pnf_cunit_main.c
│   │   ├── pnf_sim
│   │   │   ├── Makefile.am
│   │   │   ├── inc
│   │   │   │   ├── fapi_interface.h
│   │   │   │   └── fapi_stub.h
│   │   │   └── src
│   │   │       ├── fapi_stub.cpp
│   │   │       └── main.cpp
│   │   ├── sim_common
│   │   │   ├── Makefile.am
│   │   │   ├── inc
│   │   │   │   ├── pool.h
│   │   │   │   └── vendor_ext.h
│   │   │   └── src
│   │   │       └── pool.cpp
│   │   ├── utils
│   │   │   ├── CMakeLists.txt
│   │   │   ├── examples.md
│   │   │   └── nfapi_hex_parser.c
│   │   ├── vnf
│   │   │   ├── CMakeLists.txt
│   │   │   ├── Makefile.am
│   │   │   ├── inc
│   │   │   │   ├── vnf.h
│   │   │   │   └── vnf_p7.h
│   │   │   ├── public_inc
│   │   │   │   └── nfapi_vnf_interface.h
│   │   │   ├── src
│   │   │   │   ├── vnf.c
│   │   │   │   ├── vnf_interface.c
│   │   │   │   ├── vnf_p7.c
│   │   │   │   └── vnf_p7_interface.c
│   │   │   └── tests
│   │   │       ├── Makefile.am
│   │   │       └── vnf_cunit_main.c
│   │   ├── vnf_sim
│   │   │   ├── Makefile.am
│   │   │   ├── inc
│   │   │   │   └── mac.h
│   │   │   └── src
│   │   │       ├── mac.cpp
│   │   │       └── main.cpp
│   │   └── xml
│   │       ├── pnf_phy_1_A.xml
│   │       ├── pnf_phy_1_A_ws.xml
│   │       ├── pnf_phy_1_B.xml
│   │       ├── pnf_phy_2_A.xml
│   │       ├── vnf_A.xml
│   │       └── vnf_A_ws.xml
│   └── tests
│       ├── CMakeLists.txt
│       ├── nr_fapi_test.h
│       ├── p5
│       │   ├── CMakeLists.txt
│       │   ├── nr_fapi_config_request_test.c
│       │   ├── nr_fapi_config_response_test.c
│       │   ├── nr_fapi_error_indication_test.c
│       │   ├── nr_fapi_param_request_test.c
│       │   ├── nr_fapi_param_response_test.c
│       │   ├── nr_fapi_start_request_test.c
│       │   ├── nr_fapi_start_response_test.c
│       │   ├── nr_fapi_stop_indication_test.c
│       │   └── nr_fapi_stop_request_test.c
│       └── p7
│           ├── CMakeLists.txt
│           ├── dci_payload_utils.h
│           ├── nr_fapi_common_util_test.h
│           ├── nr_fapi_crc_indication_test.c
│           ├── nr_fapi_dci_inversion_test.c
│           ├── nr_fapi_dl_tti_request_test.c
│           ├── nr_fapi_rach_indication_test.c
│           ├── nr_fapi_rx_data_indication_test.c
│           ├── nr_fapi_slot_indication_test.c
│           ├── nr_fapi_srs_indication_test.c
│           ├── nr_fapi_tx_data_request_test.c
│           ├── nr_fapi_uci_indication_test.c
│           ├── nr_fapi_ul_dci_request_test.c
│           └── nr_fapi_ul_tti_request_test.c
├── oaienv
├── openair1
│   ├── CMakeLists.txt
│   ├── PHY
│   │   ├── CMakeLists.txt
│   │   ├── CODING
│   │   │   ├── 3gpplte.c
│   │   │   ├── 3gpplte_sse.c
│   │   │   ├── 3gpplte_turbo_decoder.c
│   │   │   ├── 3gpplte_turbo_decoder_avx2_16bit.c
│   │   │   ├── 3gpplte_turbo_decoder_sse.c
│   │   │   ├── 3gpplte_turbo_decoder_sse_16bit.c
│   │   │   ├── 3gpplte_turbo_decoder_sse_8bit.c
│   │   │   ├── CMakeLists.txt
│   │   │   ├── DOC
│   │   │   │   └── LDPCImplementation.md
│   │   │   ├── Makefile
│   │   │   ├── Makefile.arm
│   │   │   ├── README.txt
│   │   │   ├── TESTBENCH
│   │   │   │   ├── Makefile
│   │   │   │   ├── README.txt
│   │   │   │   ├── coding_unitary_defs.h
│   │   │   │   ├── ldpctest.c
│   │   │   │   ├── ltetest.c
│   │   │   │   ├── pdcch_test.c
│   │   │   │   ├── polartest.c
│   │   │   │   ├── smallblocktest.c
│   │   │   │   └── viterbi_test.c
│   │   │   ├── ccoding_byte.c
│   │   │   ├── ccoding_byte_lte.c
│   │   │   ├── coding_defs.h
│   │   │   ├── coding_extern.h
│   │   │   ├── coding_load.c
│   │   │   ├── crc.h
│   │   │   ├── crc_byte.c
│   │   │   ├── crcext.h
│   │   │   ├── defs_NB_IoT.h
│   │   │   ├── lte_interleaver_inline.h
│   │   │   ├── lte_rate_matching.c
│   │   │   ├── lte_segmentation.c
│   │   │   ├── lte_tf.m
│   │   │   ├── nrLDPC_coding
│   │   │   │   ├── CMakeLists.txt
│   │   │   │   ├── nrLDPC_coding_aal
│   │   │   │   │   ├── CMakeLists.txt
│   │   │   │   │   ├── README.md
│   │   │   │   │   ├── nrLDPC_coding_aal.c
│   │   │   │   │   └── nrLDPC_coding_aal.h
│   │   │   │   ├── nrLDPC_coding_interface.h
│   │   │   │   ├── nrLDPC_coding_interface_load.c
│   │   │   │   └── nrLDPC_coding_segment
│   │   │   │       ├── CMakeLists.txt
│   │   │   │       ├── nrLDPC_coding_segment_decoder.c
│   │   │   │       ├── nrLDPC_coding_segment_encoder.c
│   │   │   │       ├── nr_rate_matching.c
│   │   │   │       └── nr_rate_matching.h
│   │   │   ├── nrLDPC_decoder
│   │   │   │   ├── CMakeLists.txt
│   │   │   │   ├── doc
│   │   │   │   │   └── nrLDPC
│   │   │   │   │       ├── logo.png
│   │   │   │   │       └── nrLDPC.tex
│   │   │   │   ├── nrLDPC_bnProc.h
│   │   │   │   ├── nrLDPC_cnProc.h
│   │   │   │   ├── nrLDPC_cnProc_avx512.h
│   │   │   │   ├── nrLDPC_decoder.c
│   │   │   │   ├── nrLDPC_init.h
│   │   │   │   ├── nrLDPC_lut.h
│   │   │   │   ├── nrLDPC_mPass.h
│   │   │   │   ├── nrLDPC_tools
│   │   │   │   │   ├── CMakeLists.txt
│   │   │   │   │   ├── generator_bnProc
│   │   │   │   │   │   ├── CMakeLists.txt
│   │   │   │   │   │   ├── bnProcPc_gen_BG1_128.c
│   │   │   │   │   │   ├── bnProcPc_gen_BG1_avx2.c
│   │   │   │   │   │   ├── bnProcPc_gen_BG2_128.c
│   │   │   │   │   │   ├── bnProcPc_gen_BG2_avx2.c
│   │   │   │   │   │   ├── bnProc_gen_BG1_128.c
│   │   │   │   │   │   ├── bnProc_gen_BG1_avx2.c
│   │   │   │   │   │   ├── bnProc_gen_BG2_128.c
│   │   │   │   │   │   ├── bnProc_gen_BG2_avx2.c
│   │   │   │   │   │   ├── main.c
│   │   │   │   │   │   └── main128.c
│   │   │   │   │   ├── generator_bnProc_avx512
│   │   │   │   │   │   ├── CMakeLists.txt
│   │   │   │   │   │   ├── bnProcPc_gen_BG1_avx512.c
│   │   │   │   │   │   ├── bnProcPc_gen_BG2_avx512.c
│   │   │   │   │   │   ├── bnProc_gen_BG1_avx512.c
│   │   │   │   │   │   ├── bnProc_gen_BG2_avx512.c
│   │   │   │   │   │   └── main.c
│   │   │   │   │   ├── generator_cnProc
│   │   │   │   │   │   ├── CMakeLists.txt
│   │   │   │   │   │   ├── cnProc_gen_BG1_128.c
│   │   │   │   │   │   ├── cnProc_gen_BG1_avx2.c
│   │   │   │   │   │   ├── cnProc_gen_BG2_128.c
│   │   │   │   │   │   ├── cnProc_gen_BG2_avx2.c
│   │   │   │   │   │   ├── main.c
│   │   │   │   │   │   └── main128.c
│   │   │   │   │   ├── generator_cnProc_avx512
│   │   │   │   │   │   ├── CMakeLists.txt
│   │   │   │   │   │   ├── cnProc_gen_BG1_avx512.c
│   │   │   │   │   │   ├── cnProc_gen_BG2_avx512.c
│   │   │   │   │   │   └── main.c
│   │   │   │   │   ├── nrLDPC_debug.h
│   │   │   │   │   └── run_ldpc_generators.sh
│   │   │   │   ├── nrLDPC_types.h
│   │   │   │   └── nrLDPCdecoder_defs.h
│   │   │   ├── nrLDPC_defs.h
│   │   │   ├── nrLDPC_encoder
│   │   │   │   ├── Gen_shift_value.h
│   │   │   │   ├── ldpc176_byte.c
│   │   │   │   ├── ldpc192_byte.c
│   │   │   │   ├── ldpc192_byte_128.c
│   │   │   │   ├── ldpc208_byte.c
│   │   │   │   ├── ldpc224_byte.c
│   │   │   │   ├── ldpc224_byte_128.c
│   │   │   │   ├── ldpc240_byte.c
│   │   │   │   ├── ldpc240_byte_128.c
│   │   │   │   ├── ldpc256_byte.c
│   │   │   │   ├── ldpc256_byte_128.c
│   │   │   │   ├── ldpc288_byte.c
│   │   │   │   ├── ldpc288_byte_128.c
│   │   │   │   ├── ldpc320_byte.c
│   │   │   │   ├── ldpc320_byte_128.c
│   │   │   │   ├── ldpc352_byte.c
│   │   │   │   ├── ldpc352_byte_128.c
│   │   │   │   ├── ldpc384_alignr_byte_128.c
│   │   │   │   ├── ldpc384_byte.c
│   │   │   │   ├── ldpc384_byte_128.c
│   │   │   │   ├── ldpc384_simd512_alignr_byte.c
│   │   │   │   ├── ldpc384_simd512_byte.c
│   │   │   │   ├── ldpc384_simd512_permutex_byte.c
│   │   │   │   ├── ldpc_BG2_Zc104_byte.c
│   │   │   │   ├── ldpc_BG2_Zc112_byte.c
│   │   │   │   ├── ldpc_BG2_Zc120_byte.c
│   │   │   │   ├── ldpc_BG2_Zc128_byte.c
│   │   │   │   ├── ldpc_BG2_Zc128_byte_128.c
│   │   │   │   ├── ldpc_BG2_Zc144_byte.c
│   │   │   │   ├── ldpc_BG2_Zc160_byte.c
│   │   │   │   ├── ldpc_BG2_Zc160_byte_128.c
│   │   │   │   ├── ldpc_BG2_Zc16_byte.c
│   │   │   │   ├── ldpc_BG2_Zc176_byte.c
│   │   │   │   ├── ldpc_BG2_Zc192_byte.c
│   │   │   │   ├── ldpc_BG2_Zc192_byte_128.c
│   │   │   │   ├── ldpc_BG2_Zc208_byte.c
│   │   │   │   ├── ldpc_BG2_Zc224_byte.c
│   │   │   │   ├── ldpc_BG2_Zc224_byte_128.c
│   │   │   │   ├── ldpc_BG2_Zc240_byte.c
│   │   │   │   ├── ldpc_BG2_Zc256_byte.c
│   │   │   │   ├── ldpc_BG2_Zc256_byte_128.c
│   │   │   │   ├── ldpc_BG2_Zc288_byte.c
│   │   │   │   ├── ldpc_BG2_Zc288_byte_128.c
│   │   │   │   ├── ldpc_BG2_Zc2_byte.c
│   │   │   │   ├── ldpc_BG2_Zc320_byte.c
│   │   │   │   ├── ldpc_BG2_Zc320_byte_128.c
│   │   │   │   ├── ldpc_BG2_Zc32_byte.c
│   │   │   │   ├── ldpc_BG2_Zc32_byte_128.c
│   │   │   │   ├── ldpc_BG2_Zc352_byte.c
│   │   │   │   ├── ldpc_BG2_Zc352_byte_128.c
│   │   │   │   ├── ldpc_BG2_Zc384_byte.c
│   │   │   │   ├── ldpc_BG2_Zc384_byte_128.c
│   │   │   │   ├── ldpc_BG2_Zc4_byte.c
│   │   │   │   ├── ldpc_BG2_Zc64_byte.c
│   │   │   │   ├── ldpc_BG2_Zc64_byte_128.c
│   │   │   │   ├── ldpc_BG2_Zc72_byte.c
│   │   │   │   ├── ldpc_BG2_Zc80_byte.c
│   │   │   │   ├── ldpc_BG2_Zc88_byte.c
│   │   │   │   ├── ldpc_BG2_Zc8_byte.c
│   │   │   │   ├── ldpc_BG2_Zc96_byte.c
│   │   │   │   ├── ldpc_BG2_Zc96_byte_128.c
│   │   │   │   ├── ldpc_encode_parity_check.c
│   │   │   │   ├── ldpc_encoder.c
│   │   │   │   ├── ldpc_encoder_optim8segmulti.c
│   │   │   │   └── ldpc_generate_coefficient.c
│   │   │   ├── nrLDPC_extern.h
│   │   │   ├── nrLDPC_load.c
│   │   │   ├── nrPolar_tools
│   │   │   │   ├── CMakeLists.txt
│   │   │   │   ├── nr_bitwise_operations.c
│   │   │   │   ├── nr_crc_byte.c
│   │   │   │   ├── nr_polar_dci_defs.h
│   │   │   │   ├── nr_polar_decoder.c
│   │   │   │   ├── nr_polar_decoding_tools.c
│   │   │   │   ├── nr_polar_defs.h
│   │   │   │   ├── nr_polar_encoder.c
│   │   │   │   ├── nr_polar_init.c
│   │   │   │   ├── nr_polar_interleaving_pattern.c
│   │   │   │   ├── nr_polar_kernal_operation.c
│   │   │   │   ├── nr_polar_kronecker_power_matrices.c
│   │   │   │   ├── nr_polar_matrix_and_array.c
│   │   │   │   ├── nr_polar_pbch_defs.h
│   │   │   │   ├── nr_polar_procedures.c
│   │   │   │   ├── nr_polar_psbch_defs.h
│   │   │   │   ├── nr_polar_pucch_defs.h
│   │   │   │   ├── nr_polar_sequence_pattern.c
│   │   │   │   └── nr_polar_uci_defs.h
│   │   │   ├── nrSmallBlock
│   │   │   │   ├── CMakeLists.txt
│   │   │   │   ├── decodeSmallBlock.c
│   │   │   │   ├── encodeSmallBlock.c
│   │   │   │   └── nr_small_block_defs.h
│   │   │   ├── nr_segmentation.c
│   │   │   ├── types.h
│   │   │   ├── viterbi.c
│   │   │   └── viterbi_lte.c
│   │   ├── INIT
│   │   │   ├── README.txt
│   │   │   ├── defs_NB_IoT.h
│   │   │   ├── init_top.c
│   │   │   ├── lte_init.c
│   │   │   ├── lte_init_ru.c
│   │   │   ├── lte_init_ue.c
│   │   │   ├── lte_param_init.c
│   │   │   ├── lte_parms.c
│   │   │   ├── nr_init.c
│   │   │   ├── nr_init_ru.c
│   │   │   ├── nr_init_ue.c
│   │   │   ├── nr_parms.c
│   │   │   ├── nr_parms.h
│   │   │   ├── nr_phy_init.h
│   │   │   ├── phy_init.h
│   │   │   └── tests
│   │   │       ├── CMakeLists.txt
│   │   │       └── test_nr_frame_params.cpp
│   │   ├── LTE_ESTIMATION
│   │   │   ├── README.txt
│   │   │   ├── adjust_gain.c
│   │   │   ├── bf_freq_domain_filters.m
│   │   │   ├── filt16_32.h
│   │   │   ├── filt96_32.h
│   │   │   ├── filt96_32_khz_1dot25.h
│   │   │   ├── freq_domain_filters.m
│   │   │   ├── freq_equalization.c
│   │   │   ├── lte_adjust_sync_eNB.c
│   │   │   ├── lte_adjust_sync_ue.c
│   │   │   ├── lte_dl_bf_channel_estimation.c
│   │   │   ├── lte_dl_channel_estimation.c
│   │   │   ├── lte_dl_mbsfn_channel_estimation.c
│   │   │   ├── lte_eNB_measurements.c
│   │   │   ├── lte_est_freq_offset.c
│   │   │   ├── lte_estimation.h
│   │   │   ├── lte_sync_time.c
│   │   │   ├── lte_sync_timefreq.c
│   │   │   ├── lte_sync_timefreq.m
│   │   │   ├── lte_ue_measurements.c
│   │   │   ├── lte_ul_channel_estimation.c
│   │   │   └── pss6144.h
│   │   ├── LTE_REFSIG
│   │   │   ├── README.txt
│   │   │   ├── defs_NB_IoT.h
│   │   │   ├── gen_mod_table.m
│   │   │   ├── lte_dl_cell_spec.c
│   │   │   ├── lte_dl_mbsfn.c
│   │   │   ├── lte_dl_uespec.c
│   │   │   ├── lte_gold.c
│   │   │   ├── lte_gold_mbsfn.c
│   │   │   ├── lte_refsig.h
│   │   │   ├── lte_ul.m
│   │   │   ├── lte_ul_ref.c
│   │   │   ├── mod_table.h
│   │   │   └── primary_synch.m
│   │   ├── LTE_TRANSPORT
│   │   │   ├── README.txt
│   │   │   ├── dci.c
│   │   │   ├── dci.h
│   │   │   ├── dci_NB_IoT.h
│   │   │   ├── dci_tools.c
│   │   │   ├── dci_tools_common.c
│   │   │   ├── dci_tools_common_extern.h
│   │   │   ├── defs_NB_IoT.h
│   │   │   ├── dlsch_coding.c
│   │   │   ├── dlsch_modulation.c
│   │   │   ├── dlsch_scrambling.c
│   │   │   ├── dlsch_tbs.h
│   │   │   ├── dlsch_tbs_full.h
│   │   │   ├── edci.c
│   │   │   ├── group_hopping.c
│   │   │   ├── lte_mcs.c
│   │   │   ├── mdci.h
│   │   │   ├── pbch.c
│   │   │   ├── pcfich.c
│   │   │   ├── pcfich_common.c
│   │   │   ├── phich.c
│   │   │   ├── phich_common.c
│   │   │   ├── pilots.c
│   │   │   ├── pilots_mbsfn.c
│   │   │   ├── pmch.c
│   │   │   ├── pmch_common.c
│   │   │   ├── power_control.c
│   │   │   ├── prach.c
│   │   │   ├── prach_common.c
│   │   │   ├── prach_extern.h
│   │   │   ├── proto_NB_IoT.h
│   │   │   ├── pss.c
│   │   │   ├── pucch.c
│   │   │   ├── pucch_common.c
│   │   │   ├── pucch_extern.h
│   │   │   ├── rar_tools.c
│   │   │   ├── sss.c
│   │   │   ├── sss_gen.c
│   │   │   ├── transport_common.h
│   │   │   ├── transport_common_proto.h
│   │   │   ├── transport_eNB.h
│   │   │   ├── transport_proto.h
│   │   │   ├── transport_vars.h
│   │   │   ├── uci_NB_IoT.h
│   │   │   ├── uci_common.h
│   │   │   ├── uci_tools.c
│   │   │   ├── ulsch_decoding.c
│   │   │   ├── ulsch_demodulation.c
│   │   │   └── vrb_maps.m
│   │   ├── LTE_UE_TRANSPORT
│   │   │   ├── dci_tools_ue.c
│   │   │   ├── dci_ue.c
│   │   │   ├── dlsch_decoding.c
│   │   │   ├── dlsch_demodulation.c
│   │   │   ├── dlsch_llr_computation.c
│   │   │   ├── dlsch_llr_computation_avx2.c
│   │   │   ├── drs_modulation.c
│   │   │   ├── get_pmi.c
│   │   │   ├── initial_sync.c
│   │   │   ├── pbch_ue.c
│   │   │   ├── pcfich_ue.c
│   │   │   ├── pch_ue.c
│   │   │   ├── phich_ue.c
│   │   │   ├── pmch_ue.c
│   │   │   ├── prach_ue.c
│   │   │   ├── pucch_ue.c
│   │   │   ├── rar_tools_ue.c
│   │   │   ├── sldch.c
│   │   │   ├── slsch.c
│   │   │   ├── slss.c
│   │   │   ├── srs_modulation.c
│   │   │   ├── sss_ue.c
│   │   │   ├── transport_proto_ue.h
│   │   │   ├── transport_ue.h
│   │   │   ├── uci_tools_ue.c
│   │   │   ├── ulsch_coding.c
│   │   │   └── ulsch_modulation.c
│   │   ├── MODULATION
│   │   │   ├── CMakeLists.txt
│   │   │   ├── beamforming.c
│   │   │   ├── compute_bf_weights.c
│   │   │   ├── gen_75KHz.cpp
│   │   │   ├── modulation_UE.h
│   │   │   ├── modulation_common.h
│   │   │   ├── modulation_eNB.h
│   │   │   ├── modulation_extern.h
│   │   │   ├── nr_beamforming.c
│   │   │   ├── nr_modulation.c
│   │   │   ├── nr_modulation.h
│   │   │   ├── ofdm_mod.c
│   │   │   ├── slot_fep.c
│   │   │   ├── slot_fep_mbsfn.c
│   │   │   ├── slot_fep_nr.c
│   │   │   ├── slot_fep_ul.c
│   │   │   ├── tests
│   │   │   │   ├── CMakeLists.txt
│   │   │   │   └── test_nr_modulation.cpp
│   │   │   ├── ul_7_5_kHz.c
│   │   │   └── ul_7_5_kHz_ue.c
│   │   ├── NR_ESTIMATION
│   │   │   ├── nr_freq_equalization.c
│   │   │   ├── nr_measurements_gNB.c
│   │   │   ├── nr_ul_channel_estimation.c
│   │   │   └── nr_ul_estimation.h
│   │   ├── NR_REFSIG
│   │   │   ├── README
│   │   │   ├── dmrs_nr.c
│   │   │   ├── dmrs_nr.h
│   │   │   ├── nr_dmrs_rx.c
│   │   │   ├── nr_gen_mod_table.c
│   │   │   ├── nr_gen_mod_table.m
│   │   │   ├── nr_gold_ue.c
│   │   │   ├── nr_mod_table.h
│   │   │   ├── nr_refsig.h
│   │   │   ├── pss_nr.h
│   │   │   ├── ptrs_nr.c
│   │   │   ├── ptrs_nr.h
│   │   │   ├── refsig.c
│   │   │   ├── sl_refsig_defs.h
│   │   │   ├── ss_pbch_nr.h
│   │   │   ├── sss_nr.h
│   │   │   ├── ul_ref_seq_nr.c
│   │   │   └── ul_ref_seq_nr.h
│   │   ├── NR_TRANSPORT
│   │   │   ├── CMakeLists.txt
│   │   │   ├── README
│   │   │   ├── nr_dci.c
│   │   │   ├── nr_dci.h
│   │   │   ├── nr_dci_tools.c
│   │   │   ├── nr_dlsch.c
│   │   │   ├── nr_dlsch.h
│   │   │   ├── nr_dlsch_coding.c
│   │   │   ├── nr_pbch.c
│   │   │   ├── nr_prach.c
│   │   │   ├── nr_prach.h
│   │   │   ├── nr_prach_common.c
│   │   │   ├── nr_prs.c
│   │   │   ├── nr_pss.c
│   │   │   ├── nr_sch_dmrs.c
│   │   │   ├── nr_sch_dmrs.h
│   │   │   ├── nr_scrambling.c
│   │   │   ├── nr_sss.c
│   │   │   ├── nr_tbs_tools.c
│   │   │   ├── nr_transport_common_proto.h
│   │   │   ├── nr_transport_proto.h
│   │   │   ├── nr_uci_tools_common.c
│   │   │   ├── nr_ulsch.c
│   │   │   ├── nr_ulsch.h
│   │   │   ├── nr_ulsch_decoding.c
│   │   │   ├── nr_ulsch_demodulation.c
│   │   │   ├── nr_ulsch_llr_computation.c
│   │   │   ├── pucch_rx.c
│   │   │   ├── srs_rx.c
│   │   │   └── tests
│   │   │       ├── CMakeLists.txt
│   │   │       └── test_llr.cpp
│   │   ├── NR_UE_ESTIMATION
│   │   │   ├── filt16a_32.h
│   │   │   ├── nr_adjust_gain.c
│   │   │   ├── nr_adjust_synch_ue.c
│   │   │   ├── nr_dl_channel_estimation.c
│   │   │   ├── nr_estimation.h
│   │   │   ├── nr_ue_measurements.c
│   │   │   └── plot_prs_Ttracer_dumps.m
│   │   ├── NR_UE_TRANSPORT
│   │   │   ├── cic_filter_nr.c
│   │   │   ├── cic_filter_nr.h
│   │   │   ├── csi_rx.c
│   │   │   ├── dci_nr.c
│   │   │   ├── nr_dlsch_decoding.c
│   │   │   ├── nr_dlsch_demodulation.c
│   │   │   ├── nr_initial_sync.c
│   │   │   ├── nr_initial_sync_sl.c
│   │   │   ├── nr_ntn_l1.c
│   │   │   ├── nr_pbch.c
│   │   │   ├── nr_prach.c
│   │   │   ├── nr_psbch_rx.c
│   │   │   ├── nr_psbch_tx.c
│   │   │   ├── nr_transport_proto_ue.h
│   │   │   ├── nr_transport_ue.h
│   │   │   ├── nr_ue_rf_helpers.c
│   │   │   ├── nr_ulsch_coding.c
│   │   │   ├── nr_ulsch_ue.c
│   │   │   ├── pss_nr.c
│   │   │   ├── pucch_nr.c
│   │   │   ├── pucch_nr.h
│   │   │   └── sss_nr.c
│   │   ├── TOOLS
│   │   │   ├── CMakeLists.txt
│   │   │   ├── Makefile
│   │   │   ├── alaw_lut.h
│   │   │   ├── angle.c
│   │   │   ├── calibration_scope.c
│   │   │   ├── calibration_scope.h
│   │   │   ├── calibration_test.c
│   │   │   ├── cdot_prod.c
│   │   │   ├── costable.h
│   │   │   ├── dB_routines.c
│   │   │   ├── dfts_load.c
│   │   │   ├── file_output.c
│   │   │   ├── get_sin_cos.c
│   │   │   ├── imscope
│   │   │   │   ├── CMakeLists.txt
│   │   │   │   ├── imgui.ini
│   │   │   │   ├── imscope.cpp
│   │   │   │   ├── imscope_common.cpp
│   │   │   │   ├── imscope_init.cpp
│   │   │   │   ├── imscope_internal.h
│   │   │   │   ├── imscope_iq_file_viewer.cpp
│   │   │   │   ├── imscope_record.cpp
│   │   │   │   └── imscope_screenshot.png
│   │   │   ├── invSqrt.c
│   │   │   ├── log2_approx.c
│   │   │   ├── lte_enb_scope.c
│   │   │   ├── lte_phy_scope.c
│   │   │   ├── lte_phy_scope.h
│   │   │   ├── lte_phy_scope_tm4.c
│   │   │   ├── lte_ue_scope.c
│   │   │   ├── nr_phy_scope.c
│   │   │   ├── nr_phy_scope.h
│   │   │   ├── oai_arith_operations.c
│   │   │   ├── oai_dfts.c
│   │   │   ├── oai_dfts_neon.c
│   │   │   ├── phy_scope.h
│   │   │   ├── phy_scope_interface.c
│   │   │   ├── phy_scope_interface.h
│   │   │   ├── phy_test_tools.hpp
│   │   │   ├── readme.md
│   │   │   ├── signal_energy.c
│   │   │   ├── smbv.c
│   │   │   ├── smbv.h
│   │   │   ├── sqrt.c
│   │   │   ├── tests
│   │   │   │   ├── CMakeLists.txt
│   │   │   │   ├── benchmark_channel_pipeline.cpp
│   │   │   │   ├── benchmark_rotate_vector.cpp
│   │   │   │   ├── test_channel_pipeline.cpp
│   │   │   │   ├── test_channel_pipeline_tools.c
│   │   │   │   ├── test_channel_pipeline_tools.h
│   │   │   │   ├── test_channel_scalability.c
│   │   │   │   ├── test_channel_simulation.c
│   │   │   │   ├── test_dft.c
│   │   │   │   ├── test_log2_approx.cpp
│   │   │   │   ├── test_multipath.c
│   │   │   │   ├── test_noise.c
│   │   │   │   ├── test_oai_arith_operations.cpp
│   │   │   │   ├── test_signal_energy.cpp
│   │   │   │   ├── test_sse_intrinsics.cpp
│   │   │   │   └── test_vector_op.cpp
│   │   │   └── tools_defs.h
│   │   ├── defs_L1_NB_IoT.h
│   │   ├── defs_RU.h
│   │   ├── defs_UE.h
│   │   ├── defs_common.h
│   │   ├── defs_eNB.h
│   │   ├── defs_gNB.h
│   │   ├── defs_nr_UE.h
│   │   ├── defs_nr_common.h
│   │   ├── defs_nr_sl_UE.h
│   │   ├── gold.h
│   │   ├── if4_tools.c
│   │   ├── if4_tools.h
│   │   ├── impl_defs_lte_NB_IoT.h
│   │   ├── impl_defs_nr.h
│   │   ├── impl_defs_top.h
│   │   ├── impl_defs_top_NB_IoT.h
│   │   ├── nr_phy_common
│   │   │   ├── CMakeLists.txt
│   │   │   ├── inc
│   │   │   │   ├── nr_phy_common.h
│   │   │   │   └── nr_ue_phy_meas.h
│   │   │   └── src
│   │   │       ├── nr_phy_common.c
│   │   │       ├── nr_phy_common_csirs.c
│   │   │       ├── nr_phy_common_srs.c
│   │   │       └── nr_ue_phy_meas.c
│   │   ├── phy_extern.h
│   │   ├── phy_extern_nr_ue.h
│   │   ├── phy_extern_ue.h
│   │   ├── phy_vars.h
│   │   ├── phy_vars_nr_ue.h
│   │   ├── phy_vars_ue.h
│   │   ├── sse_intrin.h
│   │   ├── types.h
│   │   └── types_NB_IoT.h
│   ├── README.TXT
│   ├── SCHED
│   │   ├── fapi_l1.c
│   │   ├── fapi_l1.h
│   │   ├── nfapi_lte_dummy.c
│   │   ├── phy_mac_stub.c
│   │   ├── phy_procedures_lte_common.c
│   │   ├── phy_procedures_lte_eNb.c
│   │   ├── prach_procedures.c
│   │   ├── ru_procedures.c
│   │   ├── sched_common.h
│   │   ├── sched_common_extern.h
│   │   └── sched_eNB.h
│   ├── SCHED_NR
│   │   ├── nr_prach_procedures.c
│   │   ├── nr_ru_procedures.c
│   │   ├── phy_frame_config_nr.c
│   │   ├── phy_frame_config_nr.h
│   │   ├── phy_procedures_nr_gNB.c
│   │   └── sched_nr.h
│   ├── SCHED_NR_UE
│   │   ├── defs.h
│   │   ├── fapi_nr_ue_l1.c
│   │   ├── fapi_nr_ue_l1.h
│   │   ├── harq_nr.c
│   │   ├── harq_nr.h
│   │   ├── phy_procedures_nr_ue.c
│   │   ├── phy_procedures_nr_ue_sl.c
│   │   ├── phy_sch_processing_time.h
│   │   ├── pucch_uci_ue_nr.c
│   │   └── pucch_uci_ue_nr.h
│   ├── SCHED_UE
│   │   ├── phy_procedures_lte_ue.c
│   │   ├── pucch_pc.c
│   │   ├── pusch_pc.c
│   │   ├── sched_UE.h
│   │   └── srs_pc.c
│   └── SIMULATION
│       ├── CMakeLists.txt
│       ├── LTE_PHY
│       │   ├── Abstraction
│       │   │   ├── Training
│       │   │   │   ├── IEEEtran.cls
│       │   │   │   ├── bare_adv.tex
│       │   │   │   ├── bare_jrnl.tex
│       │   │   │   ├── bare_jrnl_compsoc.tex
│       │   │   │   ├── create_plots.m
│       │   │   │   ├── delta_BLER_1.m
│       │   │   │   ├── polyfit_beta_training.m
│       │   │   │   ├── polyfit_delta_BLER.m
│       │   │   │   ├── sinr_Eff_Calc.m
│       │   │   │   ├── training_abstraction.m
│       │   │   │   └── training_top_script.m
│       │   │   ├── beta_training_EESM.m
│       │   │   ├── data_collection_mode5.m
│       │   │   ├── data_extraction.m
│       │   │   ├── delta_BLER.m
│       │   │   ├── delta_BLER_1.m
│       │   │   ├── demap_q.m
│       │   │   └── opposite_q.m
│       │   ├── BLER_SIMULATIONS
│       │   │   ├── AWGN
│       │   │   │   ├── AWGN_results
│       │   │   │   │   ├── bler_tx1_chan18_nrx1_mcs0.csv
│       │   │   │   │   ├── bler_tx1_chan18_nrx1_mcs1.csv
│       │   │   │   │   ├── bler_tx1_chan18_nrx1_mcs10.csv
│       │   │   │   │   ├── bler_tx1_chan18_nrx1_mcs11.csv
│       │   │   │   │   ├── bler_tx1_chan18_nrx1_mcs12.csv
│       │   │   │   │   ├── bler_tx1_chan18_nrx1_mcs13.csv
│       │   │   │   │   ├── bler_tx1_chan18_nrx1_mcs14.csv
│       │   │   │   │   ├── bler_tx1_chan18_nrx1_mcs15.csv
│       │   │   │   │   ├── bler_tx1_chan18_nrx1_mcs16.csv
│       │   │   │   │   ├── bler_tx1_chan18_nrx1_mcs17.csv
│       │   │   │   │   ├── bler_tx1_chan18_nrx1_mcs18.csv
│       │   │   │   │   ├── bler_tx1_chan18_nrx1_mcs19.csv
│       │   │   │   │   ├── bler_tx1_chan18_nrx1_mcs2.csv
│       │   │   │   │   ├── bler_tx1_chan18_nrx1_mcs20.csv
│       │   │   │   │   ├── bler_tx1_chan18_nrx1_mcs21.csv
│       │   │   │   │   ├── bler_tx1_chan18_nrx1_mcs22.csv
│       │   │   │   │   ├── bler_tx1_chan18_nrx1_mcs23.csv
│       │   │   │   │   ├── bler_tx1_chan18_nrx1_mcs24.csv
│       │   │   │   │   ├── bler_tx1_chan18_nrx1_mcs25.csv
│       │   │   │   │   ├── bler_tx1_chan18_nrx1_mcs26.csv
│       │   │   │   │   ├── bler_tx1_chan18_nrx1_mcs27.csv
│       │   │   │   │   ├── bler_tx1_chan18_nrx1_mcs28.csv
│       │   │   │   │   ├── bler_tx1_chan18_nrx1_mcs3.csv
│       │   │   │   │   ├── bler_tx1_chan18_nrx1_mcs4.csv
│       │   │   │   │   ├── bler_tx1_chan18_nrx1_mcs5.csv
│       │   │   │   │   ├── bler_tx1_chan18_nrx1_mcs6.csv
│       │   │   │   │   ├── bler_tx1_chan18_nrx1_mcs7.csv
│       │   │   │   │   ├── bler_tx1_chan18_nrx1_mcs8.csv
│       │   │   │   │   └── bler_tx1_chan18_nrx1_mcs9.csv
│       │   │   │   └── Perf_Curves_Abs
│       │   │   │       ├── awgn_bler_tx1_mcs0.csv
│       │   │   │       ├── awgn_bler_tx1_mcs1.csv
│       │   │   │       ├── awgn_bler_tx1_mcs10.csv
│       │   │   │       ├── awgn_bler_tx1_mcs11.csv
│       │   │   │       ├── awgn_bler_tx1_mcs12.csv
│       │   │   │       ├── awgn_bler_tx1_mcs13.csv
│       │   │   │       ├── awgn_bler_tx1_mcs14.csv
│       │   │   │       ├── awgn_bler_tx1_mcs15.csv
│       │   │   │       ├── awgn_bler_tx1_mcs16.csv
│       │   │   │       ├── awgn_bler_tx1_mcs17.csv
│       │   │   │       ├── awgn_bler_tx1_mcs18.csv
│       │   │   │       ├── awgn_bler_tx1_mcs19.csv
│       │   │   │       ├── awgn_bler_tx1_mcs2.csv
│       │   │   │       ├── awgn_bler_tx1_mcs20.csv
│       │   │   │       ├── awgn_bler_tx1_mcs21.csv
│       │   │   │       ├── awgn_bler_tx1_mcs22.csv
│       │   │   │       ├── awgn_bler_tx1_mcs23.csv
│       │   │   │       ├── awgn_bler_tx1_mcs24.csv
│       │   │   │       ├── awgn_bler_tx1_mcs25.csv
│       │   │   │       ├── awgn_bler_tx1_mcs26.csv
│       │   │   │       ├── awgn_bler_tx1_mcs27.csv
│       │   │   │       ├── awgn_bler_tx1_mcs3.csv
│       │   │   │       ├── awgn_bler_tx1_mcs4.csv
│       │   │   │       ├── awgn_bler_tx1_mcs5.csv
│       │   │   │       ├── awgn_bler_tx1_mcs6.csv
│       │   │   │       ├── awgn_bler_tx1_mcs7.csv
│       │   │   │       ├── awgn_bler_tx1_mcs8.csv
│       │   │   │       └── awgn_bler_tx1_mcs9.csv
│       │   │   ├── bler_0.m
│       │   │   ├── bler_100.m
│       │   │   ├── bler_119.m
│       │   │   ├── bler_150.m
│       │   │   ├── bler_200.m
│       │   │   ├── bler_250.m
│       │   │   ├── bler_300.m
│       │   │   ├── bler_350.m
│       │   │   ├── bler_400.m
│       │   │   ├── bler_450.m
│       │   │   ├── bler_500.m
│       │   │   ├── bler_550.m
│       │   │   ├── bler_66.m
│       │   │   ├── bler_80.m
│       │   │   └── eval_results.m
│       │   ├── LTE_Configuration.c
│       │   ├── LTE_Configuration.h
│       │   ├── README.txt
│       │   ├── REFERENCE_DATA
│       │   │   ├── embms.m
│       │   │   ├── embms_20_25.m
│       │   │   ├── oai_embms_r39-1.png
│       │   │   ├── pdcch_20MHz_awgn.m
│       │   │   └── pdsch.txt
│       │   ├── blerCurvesTemplate.tex
│       │   ├── blerSimus.zip
│       │   ├── common_sim.h
│       │   ├── dlsim.c
│       │   ├── dlsim_tm4.c
│       │   ├── dlsim_tm7.c
│       │   ├── dummy_functions.c
│       │   ├── fancyheadings.sty
│       │   ├── framegen.c
│       │   ├── gpib_send.c
│       │   ├── gpib_send.h
│       │   ├── launch_sim.sh
│       │   ├── mat2wv.m
│       │   ├── mbmssim.c
│       │   ├── pbch_awgn.txt
│       │   ├── pbch_awgn_interp.txt
│       │   ├── pbchsim.c
│       │   ├── pbsPhyProcSim.sh
│       │   ├── pdcch_eval_results.m
│       │   ├── pdcchsim.c
│       │   ├── plotTools
│       │   │   ├── p
│       │   │   ├── plotTool.m
│       │   │   ├── plot_channel_PePu.m
│       │   │   ├── plot_channel_SePu.m
│       │   │   ├── plot_channels.m
│       │   │   ├── plot_constellations.m
│       │   │   ├── plot_dl_ce_prec_ul.m
│       │   │   ├── plot_dl_ch_est.m
│       │   │   ├── plot_floating_point_signals.m
│       │   │   ├── plot_srs_ce.m
│       │   │   ├── plot_srs_ce_.m
│       │   │   ├── plot_srs_prec_dl.m
│       │   │   ├── plot_srs_rxF.m
│       │   │   ├── plot_tx_bf.m
│       │   │   └── plot_txdata.m
│       │   ├── prachsim.c
│       │   ├── pucchsignalgegerator.h
│       │   ├── pucchsignalgenerator.c
│       │   ├── pucchsim.c
│       │   ├── scansim.c
│       │   ├── signalanalyzer.c
│       │   ├── signalanalyzer.h
│       │   ├── syncsim.c
│       │   ├── test.c
│       │   ├── ulsignalgenerator.c
│       │   ├── ulsignalgenerator.h
│       │   ├── ulsim.c
│       │   ├── ulsim2.c
│       │   └── unitary_defs.h
│       ├── NR_PHY
│       │   ├── BLER_SIMULATIONS
│       │   │   └── AWGN
│       │   │       ├── AWGN_MIMO2x2_results
│       │   │       │   ├── mcs0_cdlc_mimo2x2_dl.csv
│       │   │       │   ├── mcs10_cdlc_mimo2x2_dl.csv
│       │   │       │   ├── mcs11_cdlc_mimo2x2_dl.csv
│       │   │       │   ├── mcs12_cdlc_mimo2x2_dl.csv
│       │   │       │   ├── mcs13_cdlc_mimo2x2_dl.csv
│       │   │       │   ├── mcs14_cdlc_mimo2x2_dl.csv
│       │   │       │   ├── mcs15_cdlc_mimo2x2_dl.csv
│       │   │       │   ├── mcs16_cdlc_mimo2x2_dl.csv
│       │   │       │   ├── mcs17_cdlc_mimo2x2_dl.csv
│       │   │       │   ├── mcs18_cdlc_mimo2x2_dl.csv
│       │   │       │   ├── mcs19_cdlc_mimo2x2_dl.csv
│       │   │       │   ├── mcs1_cdlc_mimo2x2_dl.csv
│       │   │       │   ├── mcs20_cdlc_mimo2x2_dl.csv
│       │   │       │   ├── mcs21_cdlc_mimo2x2_dl.csv
│       │   │       │   ├── mcs22_cdlc_mimo2x2_dl.csv
│       │   │       │   ├── mcs23_cdlc_mimo2x2_dl.csv
│       │   │       │   ├── mcs24_cdlc_mimo2x2_dl.csv
│       │   │       │   ├── mcs25_cdlc_mimo2x2_dl.csv
│       │   │       │   ├── mcs26_cdlc_mimo2x2_dl.csv
│       │   │       │   ├── mcs27_cdlc_mimo2x2_dl.csv
│       │   │       │   ├── mcs28_cdlc_mimo2x2_dl.csv
│       │   │       │   ├── mcs2_cdlc_mimo2x2_dl.csv
│       │   │       │   ├── mcs3_cdlc_mimo2x2_dl.csv
│       │   │       │   ├── mcs4_cdlc_mimo2x2_dl.csv
│       │   │       │   ├── mcs5_cdlc_mimo2x2_dl.csv
│       │   │       │   ├── mcs6_cdlc_mimo2x2_dl.csv
│       │   │       │   ├── mcs7_cdlc_mimo2x2_dl.csv
│       │   │       │   ├── mcs8_cdlc_mimo2x2_dl.csv
│       │   │       │   └── mcs9_cdlc_mimo2x2_dl.csv
│       │   │       ├── AWGN_results
│       │   │       │   ├── mcs0_awgn_5G.csv
│       │   │       │   ├── mcs10_awgn_5G.csv
│       │   │       │   ├── mcs11_awgn_5G.csv
│       │   │       │   ├── mcs12_awgn_5G.csv
│       │   │       │   ├── mcs13_awgn_5G.csv
│       │   │       │   ├── mcs14_awgn_5G.csv
│       │   │       │   ├── mcs15_awgn_5G.csv
│       │   │       │   ├── mcs16_awgn_5G.csv
│       │   │       │   ├── mcs17_awgn_5G.csv
│       │   │       │   ├── mcs18_awgn_5G.csv
│       │   │       │   ├── mcs19_awgn_5G.csv
│       │   │       │   ├── mcs1_awgn_5G.csv
│       │   │       │   ├── mcs20_awgn_5G.csv
│       │   │       │   ├── mcs21_awgn_5G.csv
│       │   │       │   ├── mcs22_awgn_5G.csv
│       │   │       │   ├── mcs23_awgn_5G.csv
│       │   │       │   ├── mcs24_awgn_5G.csv
│       │   │       │   ├── mcs25_awgn_5G.csv
│       │   │       │   ├── mcs26_awgn_5G.csv
│       │   │       │   ├── mcs27_awgn_5G.csv
│       │   │       │   ├── mcs28_awgn_5G.csv
│       │   │       │   ├── mcs2_awgn_5G.csv
│       │   │       │   ├── mcs3_awgn_5G.csv
│       │   │       │   ├── mcs4_awgn_5G.csv
│       │   │       │   ├── mcs5_awgn_5G.csv
│       │   │       │   ├── mcs6_awgn_5G.csv
│       │   │       │   ├── mcs7_awgn_5G.csv
│       │   │       │   ├── mcs8_awgn_5G.csv
│       │   │       │   └── mcs9_awgn_5G.csv
│       │   │       └── README.md
│       │   ├── dlschsim.c
│       │   ├── dlsim.c
│       │   ├── nr_unitary_common.c
│       │   ├── nr_unitary_defs.h
│       │   ├── pbchsim.c
│       │   ├── prachsim.c
│       │   ├── psbchsim.c
│       │   ├── pucchsim.c
│       │   ├── reconfig.raw
│       │   ├── srssim.c
│       │   ├── ulschsim.c
│       │   └── ulsim.c
│       ├── RF
│       │   ├── Makefile
│       │   ├── README.txt
│       │   ├── adc.c
│       │   ├── dac.c
│       │   ├── rf.c
│       │   └── rf.h
│       ├── TOOLS
│       │   ├── CMakeLists.txt
│       │   ├── DOC
│       │   │   ├── channel_simulation.md
│       │   │   └── gpu_acceleration.md
│       │   ├── abstraction.c
│       │   ├── ch_desc_proto.c
│       │   ├── channel_pipeline.c
│       │   ├── channel_pipeline.cu
│       │   ├── channel_pipeline.h
│       │   ├── channel_pipeline_v2.cu
│       │   ├── channel_sim.c
│       │   ├── corr_mat.m
│       │   ├── gauss.c
│       │   ├── llr_quantization.c
│       │   ├── multipath_channel.c
│       │   ├── multipath_channel.cu
│       │   ├── multipath_tv_channel.c
│       │   ├── noise_device.c
│       │   ├── noise_device.h
│       │   ├── oai_cuda.h
│       │   ├── phase_noise.c
│       │   ├── phase_noise.cu
│       │   ├── random_channel.c
│       │   ├── rangen_double.c
│       │   ├── scm.m
│       │   ├── scm_corrmat.h
│       │   ├── sim.h
│       │   ├── taus.c
│       │   ├── uci_on_pusch_decode.m
│       │   └── uci_on_pusch_encode.m
│       └── tests
│           ├── CMakeLists.txt
│           ├── RunTimedTest.cmake
│           ├── ThresholdsCuda.cmake
│           ├── ThresholdsGracehopper.cmake
│           ├── ThresholdsOffload.cmake
│           └── analyze-timing.sh
├── openair2
│   ├── CMakeLists.txt
│   ├── COMMON
│   │   ├── as_message.h
│   │   ├── commonDef.h
│   │   ├── e1ap_messages_def.h
│   │   ├── e1ap_messages_types.h
│   │   ├── f1ap_messages_def.h
│   │   ├── f1ap_messages_types.h
│   │   ├── gtpv1_u_messages_def.h
│   │   ├── gtpv1_u_messages_types.h
│   │   ├── m2ap_messages_def.h
│   │   ├── m2ap_messages_types.h
│   │   ├── m3ap_messages_def.h
│   │   ├── m3ap_messages_types.h
│   │   ├── mac_messages_def.h
│   │   ├── mac_messages_types.h
│   │   ├── mac_rlc_primitives.h
│   │   ├── mac_rrc_primitives.h
│   │   ├── nas_messages_def.h
│   │   ├── nas_messages_types.h
│   │   ├── networkDef.h
│   │   ├── ngap_messages_def.h
│   │   ├── ngap_messages_types.h
│   │   ├── nrppa_messages_def.h
│   │   ├── nrppa_messages_types.h
│   │   ├── pdcp_messages_def.h
│   │   ├── pdcp_messages_types.h
│   │   ├── positioning_nr_paramdef.h
│   │   ├── prs_nr_paramdef.h
│   │   ├── rrc_messages_def.h
│   │   ├── rrc_messages_types.h
│   │   ├── rrm_constants.h
│   │   ├── s1ap_messages_def.h
│   │   ├── s1ap_messages_types.h
│   │   ├── sctp_messages_def.h
│   │   ├── sctp_messages_types.h
│   │   ├── x2ap_messages_def.h
│   │   ├── x2ap_messages_types.h
│   │   └── xnap_messages_types.h
│   ├── E1AP
│   │   ├── CMakeLists.txt
│   │   ├── MESSAGES
│   │   │   ├── ASN.1
│   │   │   │   ├── 38463-g80.R16.78.0.asn
│   │   │   │   └── 38463-g80.R16.78.0.cmake
│   │   │   └── CMakeLists.txt
│   │   ├── e1ap.c
│   │   ├── e1ap.h
│   │   ├── e1ap_asnc.h
│   │   ├── e1ap_common.c
│   │   ├── e1ap_common.h
│   │   ├── e1ap_default_values.h
│   │   ├── e1ap_setup.c
│   │   ├── lib
│   │   │   ├── CMakeLists.txt
│   │   │   ├── e1ap_bearer_context_management.c
│   │   │   ├── e1ap_bearer_context_management.h
│   │   │   ├── e1ap_interface_management.c
│   │   │   ├── e1ap_interface_management.h
│   │   │   ├── e1ap_lib_common.c
│   │   │   ├── e1ap_lib_common.h
│   │   │   └── e1ap_lib_includes.h
│   │   └── tests
│   │       ├── CMakeLists.txt
│   │       └── e1ap_lib_test.c
│   ├── E2AP
│   │   ├── CMakeLists.txt
│   │   ├── RAN_FUNCTION
│   │   │   ├── CMakeLists.txt
│   │   │   ├── CUSTOMIZED
│   │   │   │   ├── ran_func_gtp.c
│   │   │   │   ├── ran_func_gtp.h
│   │   │   │   ├── ran_func_mac.c
│   │   │   │   ├── ran_func_mac.h
│   │   │   │   ├── ran_func_pdcp.c
│   │   │   │   ├── ran_func_pdcp.h
│   │   │   │   ├── ran_func_rlc.c
│   │   │   │   ├── ran_func_rlc.h
│   │   │   │   ├── ran_func_slice.c
│   │   │   │   ├── ran_func_slice.h
│   │   │   │   ├── ran_func_tc.c
│   │   │   │   └── ran_func_tc.h
│   │   │   ├── O-RAN
│   │   │   │   ├── README.md
│   │   │   │   ├── ran_e2sm_ue_id.c
│   │   │   │   ├── ran_e2sm_ue_id.h
│   │   │   │   ├── ran_func_kpm.c
│   │   │   │   ├── ran_func_kpm.h
│   │   │   │   ├── ran_func_kpm_subs.c
│   │   │   │   ├── ran_func_kpm_subs.h
│   │   │   │   ├── ran_func_rc.c
│   │   │   │   ├── ran_func_rc.h
│   │   │   │   ├── ran_func_rc_extern.h
│   │   │   │   ├── ran_func_rc_subs.c
│   │   │   │   └── ran_func_rc_subs.h
│   │   │   ├── init_ran_func.c
│   │   │   ├── init_ran_func.h
│   │   │   ├── read_setup_ran.c
│   │   │   └── read_setup_ran.h
│   │   ├── README.md
│   │   ├── e2_agent_arg.c
│   │   ├── e2_agent_arg.h
│   │   ├── e2_agent_paramdef.h
│   │   └── flexric
│   ├── ENB_APP
│   │   ├── L1_paramdef.h
│   │   ├── MACRLC_paramdef.h
│   │   ├── NB_IoT_interface.c
│   │   ├── NB_IoT_interface.h
│   │   ├── RRC_config_tools.c
│   │   ├── RRC_config_tools.h
│   │   ├── RRC_paramsvalues.h
│   │   ├── enb_app.c
│   │   ├── enb_app.h
│   │   ├── enb_config.c
│   │   ├── enb_config.h
│   │   ├── enb_config_SL.c
│   │   ├── enb_config_eMTC.c
│   │   ├── enb_paramdef.h
│   │   ├── enb_paramdef_emtc.h
│   │   ├── enb_paramdef_mce.h
│   │   ├── enb_paramdef_mme.h
│   │   └── enb_paramdef_sidelink.h
│   ├── F1AP
│   │   ├── CMakeLists.txt
│   │   ├── MESSAGES
│   │   │   ├── ASN1
│   │   │   │   ├── R15.1.1
│   │   │   │   │   ├── F1AP-CommonDataTypes.asn
│   │   │   │   │   ├── F1AP-Constants.asn
│   │   │   │   │   ├── F1AP-Containers.asn
│   │   │   │   │   ├── F1AP-IEs.asn
│   │   │   │   │   ├── F1AP-PDU-Contents.asn
│   │   │   │   │   ├── F1AP-PDU-Descriptions.asn
│   │   │   │   │   └── asn1_constants.h
│   │   │   │   ├── R15.2.1
│   │   │   │   │   ├── F1AP-CommonDataTypes.asn
│   │   │   │   │   ├── F1AP-Constants.asn
│   │   │   │   │   ├── F1AP-Containers.asn
│   │   │   │   │   ├── F1AP-IEs.asn
│   │   │   │   │   ├── F1AP-PDU-Contents.asn
│   │   │   │   │   └── F1AP-PDU-Descriptions.asn
│   │   │   │   ├── R16.21.0
│   │   │   │   │   └── f1ap-16.21.0.asn
│   │   │   │   ├── R16.3.1
│   │   │   │   │   ├── 38473-g31.asn
│   │   │   │   │   ├── F1AP-CommonDataTypes.asn
│   │   │   │   │   ├── F1AP-Constants.asn
│   │   │   │   │   ├── F1AP-Containers.asn
│   │   │   │   │   ├── F1AP-IEs.asn
│   │   │   │   │   ├── F1AP-PDU-Contents.asn
│   │   │   │   │   └── F1AP-PDU-Descriptions.asn
│   │   │   │   ├── f1ap-16.21.0.cmake
│   │   │   │   └── f1ap-16.3.1.cmake
│   │   │   └── CMakeLists.txt
│   │   ├── f1ap_common.c
│   │   ├── f1ap_common.h
│   │   ├── f1ap_cu_interface_management.c
│   │   ├── f1ap_cu_interface_management.h
│   │   ├── f1ap_cu_paging.c
│   │   ├── f1ap_cu_paging.h
│   │   ├── f1ap_cu_rrc_message_transfer.c
│   │   ├── f1ap_cu_rrc_message_transfer.h
│   │   ├── f1ap_cu_task.c
│   │   ├── f1ap_cu_task.h
│   │   ├── f1ap_cu_ue_context_management.c
│   │   ├── f1ap_cu_ue_context_management.h
│   │   ├── f1ap_default_values.h
│   │   ├── f1ap_du_interface_management.c
│   │   ├── f1ap_du_interface_management.h
│   │   ├── f1ap_du_paging.c
│   │   ├── f1ap_du_paging.h
│   │   ├── f1ap_du_rrc_message_transfer.c
│   │   ├── f1ap_du_rrc_message_transfer.h
│   │   ├── f1ap_du_task.c
│   │   ├── f1ap_du_task.h
│   │   ├── f1ap_du_ue_context_management.c
│   │   ├── f1ap_du_ue_context_management.h
│   │   ├── f1ap_encoder.c
│   │   ├── f1ap_encoder.h
│   │   ├── f1ap_handlers.c
│   │   ├── f1ap_ids.c
│   │   ├── f1ap_ids.h
│   │   ├── f1ap_ids_test.c
│   │   ├── f1ap_itti_messaging.c
│   │   ├── f1ap_itti_messaging.h
│   │   ├── lib
│   │   │   ├── CMakeLists.txt
│   │   │   ├── f1ap_interface_management.c
│   │   │   ├── f1ap_interface_management.h
│   │   │   ├── f1ap_lib_common.c
│   │   │   ├── f1ap_lib_common.h
│   │   │   ├── f1ap_lib_includes.h
│   │   │   ├── f1ap_paging.c
│   │   │   ├── f1ap_paging.h
│   │   │   ├── f1ap_positioning.c
│   │   │   ├── f1ap_positioning.h
│   │   │   ├── f1ap_rrc_message_transfer.c
│   │   │   ├── f1ap_rrc_message_transfer.h
│   │   │   ├── f1ap_ue_context.c
│   │   │   └── f1ap_ue_context.h
│   │   └── tests
│   │       ├── CMakeLists.txt
│   │       └── f1ap_lib_test.c
│   ├── GNB_APP
│   │   ├── L1_nr_paramdef.h
│   │   ├── MACRLC_nr_paramdef.h
│   │   ├── RRC_nr_paramsvalues.h
│   │   ├── gnb_app.c
│   │   ├── gnb_app.h
│   │   ├── gnb_config.c
│   │   ├── gnb_config.h
│   │   ├── gnb_config_common.c
│   │   ├── gnb_config_common.h
│   │   ├── gnb_config_ng.c
│   │   ├── gnb_config_ng.h
│   │   └── gnb_paramdef.h
│   ├── LAYER2
│   │   ├── CMakeLists.txt
│   │   ├── MAC
│   │   │   ├── config.c
│   │   │   ├── config_NB_IoT.h
│   │   │   ├── config_ue.c
│   │   │   ├── defs_NB_IoT.h
│   │   │   ├── dummy_functions.c
│   │   │   ├── eNB_scheduler.c
│   │   │   ├── eNB_scheduler_RA.c
│   │   │   ├── eNB_scheduler_bch.c
│   │   │   ├── eNB_scheduler_dlsch.c
│   │   │   ├── eNB_scheduler_fairRR.c
│   │   │   ├── eNB_scheduler_fairRR.h
│   │   │   ├── eNB_scheduler_mch.c
│   │   │   ├── eNB_scheduler_phytest.c
│   │   │   ├── eNB_scheduler_primitives.c
│   │   │   ├── eNB_scheduler_ulsch.c
│   │   │   ├── l1_helpers.c
│   │   │   ├── mac.h
│   │   │   ├── mac_extern.h
│   │   │   ├── mac_proto.h
│   │   │   ├── main.c
│   │   │   ├── main_ue.c
│   │   │   ├── pre_processor.c
│   │   │   ├── proto_NB_IoT.h
│   │   │   ├── ra_procedures.c
│   │   │   ├── rar_tools.c
│   │   │   ├── rar_tools_ue.c
│   │   │   ├── slicing
│   │   │   │   ├── slicing.c
│   │   │   │   ├── slicing.h
│   │   │   │   └── slicing_internal.h
│   │   │   └── ue_procedures.c
│   │   ├── NR_MAC_COMMON
│   │   │   ├── nr_compute_tbs_common.c
│   │   │   ├── nr_mac.h
│   │   │   ├── nr_mac_common.c
│   │   │   ├── nr_mac_common.h
│   │   │   ├── nr_mac_common_tdd.c
│   │   │   └── nr_prach_config.h
│   │   ├── NR_MAC_UE
│   │   │   ├── CMakeLists.txt
│   │   │   ├── config_ue.c
│   │   │   ├── config_ue_sl.c
│   │   │   ├── mac_defs.h
│   │   │   ├── mac_defs_sl.h
│   │   │   ├── mac_proto.h
│   │   │   ├── mac_tables.c
│   │   │   ├── main_ue_nr.c
│   │   │   ├── nr_ra_procedures.c
│   │   │   ├── nr_ue_dci_configuration.c
│   │   │   ├── nr_ue_power_procedures.c
│   │   │   ├── nr_ue_procedures.c
│   │   │   ├── nr_ue_procedures_sl.c
│   │   │   ├── nr_ue_scheduler.c
│   │   │   ├── nr_ue_scheduler_sl.c
│   │   │   └── tests
│   │   │       ├── CMakeLists.txt
│   │   │       ├── test_nr_ue_power_procedures.cpp
│   │   │       └── test_nr_ue_ra_procedures.cpp
│   │   ├── NR_MAC_gNB
│   │   │   ├── config.c
│   │   │   ├── gNB_scheduler.c
│   │   │   ├── gNB_scheduler_RA.c
│   │   │   ├── gNB_scheduler_bch.c
│   │   │   ├── gNB_scheduler_dlsch.c
│   │   │   ├── gNB_scheduler_dlsch_default_policies.c
│   │   │   ├── gNB_scheduler_dlsch_default_policies.h
│   │   │   ├── gNB_scheduler_phytest.c
│   │   │   ├── gNB_scheduler_primitives.c
│   │   │   ├── gNB_scheduler_srs.c
│   │   │   ├── gNB_scheduler_uci.c
│   │   │   ├── gNB_scheduler_ulsch.c
│   │   │   ├── gNB_scheduler_ulsch_default_policies.c
│   │   │   ├── gNB_scheduler_ulsch_default_policies.h
│   │   │   ├── mac_config.h
│   │   │   ├── mac_proto.h
│   │   │   ├── mac_rrc_dl_handler.c
│   │   │   ├── mac_rrc_dl_handler.h
│   │   │   ├── mac_rrc_ul.h
│   │   │   ├── mac_rrc_ul_direct.c
│   │   │   ├── mac_rrc_ul_f1ap.c
│   │   │   ├── main.c
│   │   │   ├── nr_mac_gNB.h
│   │   │   ├── nr_radio_config.c
│   │   │   └── nr_radio_config.h
│   │   ├── PDCP_v10.1.0
│   │   │   ├── pdcp.c
│   │   │   ├── pdcp.h
│   │   │   ├── pdcp_fifo.c
│   │   │   ├── pdcp_primitives.c
│   │   │   ├── pdcp_primitives.h
│   │   │   ├── pdcp_security.c
│   │   │   ├── pdcp_sequence_manager.c
│   │   │   ├── pdcp_sequence_manager.h
│   │   │   ├── pdcp_util.c
│   │   │   └── pdcp_util.h
│   │   ├── RLC
│   │   │   └── rlc.h
│   │   ├── nr_pdcp
│   │   │   ├── CMakeLists.txt
│   │   │   ├── asn1_utils.c
│   │   │   ├── cucp_cuup_handler.c
│   │   │   ├── cucp_cuup_handler.h
│   │   │   ├── cuup_cucp_direct.c
│   │   │   ├── cuup_cucp_e1ap.c
│   │   │   ├── cuup_cucp_if.c
│   │   │   ├── cuup_cucp_if.h
│   │   │   ├── nr_pdcp.h
│   │   │   ├── nr_pdcp_asn1_utils.h
│   │   │   ├── nr_pdcp_configuration.h
│   │   │   ├── nr_pdcp_entity.c
│   │   │   ├── nr_pdcp_entity.h
│   │   │   ├── nr_pdcp_integrity_data.h
│   │   │   ├── nr_pdcp_integrity_nia1.c
│   │   │   ├── nr_pdcp_integrity_nia1.h
│   │   │   ├── nr_pdcp_integrity_nia2.c
│   │   │   ├── nr_pdcp_integrity_nia2.h
│   │   │   ├── nr_pdcp_oai_api.c
│   │   │   ├── nr_pdcp_oai_api.h
│   │   │   ├── nr_pdcp_sdu.c
│   │   │   ├── nr_pdcp_sdu.h
│   │   │   ├── nr_pdcp_security_nea1.c
│   │   │   ├── nr_pdcp_security_nea1.h
│   │   │   ├── nr_pdcp_security_nea2.c
│   │   │   ├── nr_pdcp_security_nea2.h
│   │   │   ├── nr_pdcp_timer_thread.c
│   │   │   ├── nr_pdcp_timer_thread.h
│   │   │   ├── nr_pdcp_ue_manager.c
│   │   │   ├── nr_pdcp_ue_manager.h
│   │   │   └── tests
│   │   │       ├── CMakeLists.txt
│   │   │       └── snow3g_tests.c
│   │   ├── nr_rlc
│   │   │   ├── CMakeLists.txt
│   │   │   ├── Makefile
│   │   │   ├── TODO
│   │   │   ├── asn1_utils.c
│   │   │   ├── nr_rlc_asn1_utils.h
│   │   │   ├── nr_rlc_configuration.h
│   │   │   ├── nr_rlc_entity.c
│   │   │   ├── nr_rlc_entity.h
│   │   │   ├── nr_rlc_entity_am.c
│   │   │   ├── nr_rlc_entity_am.h
│   │   │   ├── nr_rlc_entity_tm.c
│   │   │   ├── nr_rlc_entity_tm.h
│   │   │   ├── nr_rlc_entity_um.c
│   │   │   ├── nr_rlc_entity_um.h
│   │   │   ├── nr_rlc_oai_api.c
│   │   │   ├── nr_rlc_oai_api.h
│   │   │   ├── nr_rlc_pdu.c
│   │   │   ├── nr_rlc_pdu.h
│   │   │   ├── nr_rlc_rx_manager.c
│   │   │   ├── nr_rlc_rx_manager.h
│   │   │   ├── nr_rlc_sdu.c
│   │   │   ├── nr_rlc_sdu.h
│   │   │   ├── nr_rlc_ue_manager.c
│   │   │   ├── nr_rlc_ue_manager.h
│   │   │   ├── test.c
│   │   │   └── tests
│   │   │       ├── CMakeLists.txt
│   │   │       ├── LOG
│   │   │       │   └── log.h
│   │   │       ├── Makefile
│   │   │       ├── benchmark_nr_rlc_am_entity.cpp
│   │   │       ├── exec_nr_rlc_test.sh
│   │   │       ├── run_tests.sh
│   │   │       ├── test.c
│   │   │       ├── test1.h
│   │   │       ├── test1.txt.gz
│   │   │       ├── test10.h
│   │   │       ├── test10.txt.gz
│   │   │       ├── test11.h
│   │   │       ├── test11.txt.gz
│   │   │       ├── test12.h
│   │   │       ├── test12.txt.gz
│   │   │       ├── test13.h
│   │   │       ├── test13.txt.gz
│   │   │       ├── test14.h
│   │   │       ├── test14.txt.gz
│   │   │       ├── test15.h
│   │   │       ├── test15.txt.gz
│   │   │       ├── test16.h
│   │   │       ├── test16.txt.gz
│   │   │       ├── test17.h
│   │   │       ├── test17.txt.gz
│   │   │       ├── test2.h
│   │   │       ├── test2.txt.gz
│   │   │       ├── test3.h
│   │   │       ├── test3.txt.gz
│   │   │       ├── test4.h
│   │   │       ├── test4.txt.gz
│   │   │       ├── test5.h
│   │   │       ├── test5.txt.gz
│   │   │       ├── test6.h
│   │   │       ├── test6.txt.gz
│   │   │       ├── test7.h
│   │   │       ├── test7.txt.gz
│   │   │       ├── test8.h
│   │   │       ├── test8.txt.gz
│   │   │       ├── test9.h
│   │   │       ├── test9.txt.gz
│   │   │       ├── test_nr_rlc_am_entity.cpp
│   │   │       └── time_stat.c
│   │   ├── openair2_proc.c
│   │   └── rlc_v2
│   │       ├── TODO
│   │       ├── asn1_utils.c
│   │       ├── rlc_asn1_utils.h
│   │       ├── rlc_entity.c
│   │       ├── rlc_entity.h
│   │       ├── rlc_entity_am.c
│   │       ├── rlc_entity_am.h
│   │       ├── rlc_entity_um.c
│   │       ├── rlc_entity_um.h
│   │       ├── rlc_oai_api.c
│   │       ├── rlc_pdu.c
│   │       ├── rlc_pdu.h
│   │       ├── rlc_sdu.c
│   │       ├── rlc_sdu.h
│   │       ├── rlc_ue_manager.c
│   │       ├── rlc_ue_manager.h
│   │       └── tests
│   │           ├── LOG
│   │           │   └── log.h
│   │           ├── Makefile
│   │           ├── README
│   │           ├── make_pdu.c
│   │           ├── run_tests.sh
│   │           ├── test.c
│   │           ├── test1.h
│   │           ├── test1.txt.gz
│   │           ├── test10.h
│   │           ├── test10.txt.gz
│   │           ├── test11.h
│   │           ├── test11.txt.gz
│   │           ├── test12.h
│   │           ├── test12.txt.gz
│   │           ├── test13.h
│   │           ├── test13.txt.gz
│   │           ├── test14.h
│   │           ├── test14.txt.gz
│   │           ├── test15.h
│   │           ├── test15.txt.gz
│   │           ├── test16.h
│   │           ├── test16.txt.gz
│   │           ├── test17.h
│   │           ├── test17.txt.gz
│   │           ├── test18.h
│   │           ├── test18.txt.gz
│   │           ├── test19.h
│   │           ├── test19.txt.gz
│   │           ├── test2.h
│   │           ├── test2.txt.gz
│   │           ├── test20.h
│   │           ├── test20.txt.gz
│   │           ├── test21.h
│   │           ├── test21.txt.gz
│   │           ├── test22.h
│   │           ├── test22.txt.gz
│   │           ├── test23.h
│   │           ├── test23.txt.gz
│   │           ├── test24.h
│   │           ├── test24.txt.gz
│   │           ├── test25.h
│   │           ├── test25.txt.gz
│   │           ├── test26.h
│   │           ├── test26.txt.gz
│   │           ├── test27.h
│   │           ├── test27.txt.gz
│   │           ├── test28.h
│   │           ├── test28.txt.gz
│   │           ├── test29.h
│   │           ├── test29.txt.gz
│   │           ├── test3.h
│   │           ├── test3.txt.gz
│   │           ├── test30.h
│   │           ├── test30.txt.gz
│   │           ├── test31.h
│   │           ├── test31.txt.gz
│   │           ├── test32.h
│   │           ├── test32.txt.gz
│   │           ├── test33.h
│   │           ├── test33.txt.gz
│   │           ├── test34.h
│   │           ├── test34.txt.gz
│   │           ├── test35.h
│   │           ├── test35.txt.gz
│   │           ├── test36.h
│   │           ├── test36.txt.gz
│   │           ├── test37.h
│   │           ├── test37.txt.gz
│   │           ├── test38.h
│   │           ├── test38.txt.gz
│   │           ├── test39.h
│   │           ├── test39.txt.gz
│   │           ├── test4.h
│   │           ├── test4.txt.gz
│   │           ├── test40.h
│   │           ├── test40.txt.gz
│   │           ├── test41.h
│   │           ├── test41.txt.gz
│   │           ├── test42.h
│   │           ├── test42.txt.gz
│   │           ├── test43.h
│   │           ├── test43.txt.gz
│   │           ├── test44.h
│   │           ├── test44.txt.gz
│   │           ├── test45.h
│   │           ├── test45.txt.gz
│   │           ├── test46.h
│   │           ├── test46.txt.gz
│   │           ├── test47.h
│   │           ├── test47.txt.gz
│   │           ├── test48.h
│   │           ├── test48.txt.gz
│   │           ├── test49.h
│   │           ├── test49.txt.gz
│   │           ├── test5.h
│   │           ├── test5.txt.gz
│   │           ├── test6.h
│   │           ├── test6.txt.gz
│   │           ├── test7.h
│   │           ├── test7.txt.gz
│   │           ├── test8.h
│   │           ├── test8.txt.gz
│   │           ├── test9.h
│   │           └── test9.txt.gz
│   ├── M2AP
│   │   ├── CMakeLists.txt
│   │   ├── MESSAGES
│   │   │   ├── ASN1
│   │   │   │   ├── m2ap-14.0.0.asn
│   │   │   │   └── m2ap-14.0.0.cmake
│   │   │   └── CMakeLists.txt
│   │   ├── m2ap_MCE.c
│   │   ├── m2ap_MCE.h
│   │   ├── m2ap_MCE_defs.h
│   │   ├── m2ap_MCE_generate_messages.c
│   │   ├── m2ap_MCE_generate_messages.h
│   │   ├── m2ap_MCE_handler.c
│   │   ├── m2ap_MCE_handler.h
│   │   ├── m2ap_MCE_interface_management.c
│   │   ├── m2ap_MCE_interface_management.h
│   │   ├── m2ap_MCE_management_procedures.c
│   │   ├── m2ap_MCE_management_procedures.h
│   │   ├── m2ap_common.c
│   │   ├── m2ap_common.h
│   │   ├── m2ap_decoder.c
│   │   ├── m2ap_decoder.h
│   │   ├── m2ap_default_values.h
│   │   ├── m2ap_eNB.c
│   │   ├── m2ap_eNB.h
│   │   ├── m2ap_eNB_defs.h
│   │   ├── m2ap_eNB_generate_messages.c
│   │   ├── m2ap_eNB_generate_messages.h
│   │   ├── m2ap_eNB_handler.c
│   │   ├── m2ap_eNB_handler.h
│   │   ├── m2ap_eNB_interface_management.c
│   │   ├── m2ap_eNB_interface_management.h
│   │   ├── m2ap_eNB_management_procedures.c
│   │   ├── m2ap_eNB_management_procedures.h
│   │   ├── m2ap_encoder.c
│   │   ├── m2ap_encoder.h
│   │   ├── m2ap_handler.c
│   │   ├── m2ap_handler.h
│   │   ├── m2ap_ids.c
│   │   ├── m2ap_ids.h
│   │   ├── m2ap_itti_messaging.c
│   │   ├── m2ap_itti_messaging.h
│   │   ├── m2ap_timers.c
│   │   └── m2ap_timers.h
│   ├── MCE_APP
│   │   ├── mce_app.c
│   │   ├── mce_app.h
│   │   ├── mce_config.c
│   │   └── mce_config.h
│   ├── NR_PHY_INTERFACE
│   │   ├── NR_IF_Module.c
│   │   └── NR_IF_Module.h
│   ├── NR_UE_PHY_INTERFACE
│   │   ├── NR_IF_Module.c
│   │   ├── NR_IF_Module.h
│   │   ├── NR_Packet_Drop.c
│   │   └── NR_Packet_Drop.h
│   ├── PHY_INTERFACE
│   │   ├── IF_Module.c
│   │   ├── IF_Module.h
│   │   ├── IF_Module_NB_IoT.h
│   │   ├── phy_interface.h
│   │   ├── phy_interface_extern.h
│   │   ├── phy_interface_vars.h
│   │   ├── phy_stub_UE.c
│   │   ├── phy_stub_UE.h
│   │   ├── queue_t.c
│   │   ├── queue_t.h
│   │   ├── queue_test.c
│   │   └── queue_test_run
│   ├── RRC
│   │   ├── CMakeLists.txt
│   │   ├── L2_INTERFACE
│   │   │   └── openair_rrc_L2_interface.h
│   │   ├── LTE
│   │   │   ├── CMakeLists.txt
│   │   │   ├── L2_interface.c
│   │   │   ├── L2_interface_common.c
│   │   │   ├── L2_interface_ue.c
│   │   │   ├── MESSAGES
│   │   │   │   ├── ASN.1
│   │   │   │   │   ├── RRC-36331-f22.asn
│   │   │   │   │   ├── RRC-e30.asn
│   │   │   │   │   ├── extract_asn1_from_spec.pl
│   │   │   │   │   ├── lte-rrc-10.21.0.asn1
│   │   │   │   │   ├── lte-rrc-11.18.0.asn1
│   │   │   │   │   ├── lte-rrc-12.16.0.asn1
│   │   │   │   │   ├── lte-rrc-13.9.1.asn1
│   │   │   │   │   ├── lte-rrc-14.4.0.asn1
│   │   │   │   │   ├── lte-rrc-14.6.2.asn1
│   │   │   │   │   ├── lte-rrc-14.7.0.asn1
│   │   │   │   │   ├── lte-rrc-15.1.0.asn1
│   │   │   │   │   ├── lte-rrc-15.2.1.asn1
│   │   │   │   │   ├── lte-rrc-15.2.2.asn1
│   │   │   │   │   ├── lte-rrc-15.3.0.asn1
│   │   │   │   │   ├── lte-rrc-15.6.0.asn1
│   │   │   │   │   ├── lte-rrc-15.6.0.cmake
│   │   │   │   │   ├── lte-rrc-16.13.0.asn1
│   │   │   │   │   ├── lte-rrc-16.13.0.cmake
│   │   │   │   │   ├── lte-rrc-8.21.0.asn1
│   │   │   │   │   └── lte-rrc-9.18.0.asn1
│   │   │   │   ├── CMakeLists.txt
│   │   │   │   ├── README.md
│   │   │   │   ├── asn1_msg.c
│   │   │   │   ├── asn1_msg.h
│   │   │   │   ├── asn1_msg_NB_IoT.c
│   │   │   │   └── asn1_msg_NB_IoT.h
│   │   │   ├── defs_NB_IoT.h
│   │   │   ├── extern_NB_IoT.h
│   │   │   ├── plmn_data.h
│   │   │   ├── proto_NB_IoT.h
│   │   │   ├── rrc_UE.c
│   │   │   ├── rrc_common.c
│   │   │   ├── rrc_defs.h
│   │   │   ├── rrc_eNB.c
│   │   │   ├── rrc_eNB_GTPV1U.c
│   │   │   ├── rrc_eNB_GTPV1U.h
│   │   │   ├── rrc_eNB_M2AP.c
│   │   │   ├── rrc_eNB_M2AP.h
│   │   │   ├── rrc_eNB_S1AP.c
│   │   │   ├── rrc_eNB_S1AP.h
│   │   │   ├── rrc_eNB_UE_context.c
│   │   │   ├── rrc_eNB_UE_context.h
│   │   │   ├── rrc_eNB_endc.c
│   │   │   ├── rrc_extern.h
│   │   │   ├── rrc_proto.h
│   │   │   ├── rrc_types.h
│   │   │   ├── rrc_types_NB_IoT.h
│   │   │   └── rrc_vars.h
│   │   ├── NR
│   │   │   ├── CMakeLists.txt
│   │   │   ├── MESSAGES
│   │   │   │   ├── ASN.1
│   │   │   │   │   ├── NR-RRC-38331-f10.asn
│   │   │   │   │   ├── NR-RRC-38331-f21.asn
│   │   │   │   │   ├── extract_asn1_from_spce.pl
│   │   │   │   │   ├── nr-rrc-15.2.1.asn1
│   │   │   │   │   ├── nr-rrc-15.3.0.asn1
│   │   │   │   │   ├── nr-rrc-15.6.0.asn1
│   │   │   │   │   ├── nr-rrc-16.1.0.asn1
│   │   │   │   │   ├── nr-rrc-16.4.1.asn1
│   │   │   │   │   ├── nr-rrc-16.4.1.cmake
│   │   │   │   │   ├── nr-rrc-17.3.0.asn1
│   │   │   │   │   └── nr-rrc-17.3.0.cmake
│   │   │   │   ├── CMakeLists.txt
│   │   │   │   ├── asn1_msg.c
│   │   │   │   ├── asn1_msg.h
│   │   │   │   └── tests
│   │   │   │       ├── CMakeLists.txt
│   │   │   │       └── test_asn1_msg.cpp
│   │   │   ├── cucp_cuup_direct.c
│   │   │   ├── cucp_cuup_e1ap.c
│   │   │   ├── cucp_cuup_if.h
│   │   │   ├── mac_rrc_dl.h
│   │   │   ├── mac_rrc_dl_direct.c
│   │   │   ├── mac_rrc_dl_f1ap.c
│   │   │   ├── nr_rrc_common.h
│   │   │   ├── nr_rrc_defs.h
│   │   │   ├── nr_rrc_proto.h
│   │   │   ├── rrc_cell_management.c
│   │   │   ├── rrc_cell_management.h
│   │   │   ├── rrc_gNB.c
│   │   │   ├── rrc_gNB_NGAP.c
│   │   │   ├── rrc_gNB_NGAP.h
│   │   │   ├── rrc_gNB_UE_context.c
│   │   │   ├── rrc_gNB_UE_context.h
│   │   │   ├── rrc_gNB_asn1.c
│   │   │   ├── rrc_gNB_asn1.h
│   │   │   ├── rrc_gNB_cuup.c
│   │   │   ├── rrc_gNB_du.c
│   │   │   ├── rrc_gNB_du.h
│   │   │   ├── rrc_gNB_mobility.c
│   │   │   ├── rrc_gNB_mobility.h
│   │   │   ├── rrc_gNB_nsa.c
│   │   │   ├── rrc_gNB_radio_bearers.c
│   │   │   ├── rrc_gNB_radio_bearers.h
│   │   │   └── tests
│   │   │       ├── CMakeLists.txt
│   │   │       ├── rrc_bearers_test.c
│   │   │       └── rrc_cell_management_test.c
│   │   ├── NR_UE
│   │   │   ├── L2_interface_ue.c
│   │   │   ├── L2_interface_ue.h
│   │   │   ├── main_ue.c
│   │   │   ├── rrc_UE.c
│   │   │   ├── rrc_defs.h
│   │   │   ├── rrc_proto.h
│   │   │   ├── rrc_sl_preconfig.c
│   │   │   ├── rrc_timers_and_constants.c
│   │   │   ├── sl_preconfig_paramvalues.h
│   │   │   ├── verify_RRC.c
│   │   │   └── verify_RRC.h
│   │   └── common.h
│   ├── SDAP
│   │   └── nr_sdap
│   │       ├── nr_sdap.c
│   │       ├── nr_sdap.h
│   │       ├── nr_sdap_configuration.h
│   │       ├── nr_sdap_entity.c
│   │       └── nr_sdap_entity.h
│   ├── UTIL
│   │   ├── CLI
│   │   │   ├── cli.c
│   │   │   ├── cli.h
│   │   │   ├── cli_cmd.c
│   │   │   ├── cli_if.h
│   │   │   └── cli_server.c
│   │   ├── CMakeLists.txt
│   │   ├── MATH
│   │   │   ├── oml.c
│   │   │   └── oml.h
│   │   ├── OMG
│   │   │   ├── OMG_TRACE_DESCRIPTION.pdf
│   │   │   ├── README.TXT
│   │   │   ├── TRACE
│   │   │   │   ├── OMG_TRACE_update.pdf
│   │   │   │   ├── README.TXT
│   │   │   │   ├── example_trace.tr
│   │   │   │   ├── handover.tr
│   │   │   │   ├── handover_1ue.tr
│   │   │   │   ├── hexagonal_eNBs.tr
│   │   │   │   ├── mobility_2ues.tr
│   │   │   │   ├── mobility_3ues.tr
│   │   │   │   ├── regular.tr
│   │   │   │   ├── static_1enb.tr
│   │   │   │   ├── static_2ues.tr
│   │   │   │   └── zero_speed.tr
│   │   │   ├── common.c
│   │   │   ├── defs.h
│   │   │   ├── grid.c
│   │   │   ├── grid.h
│   │   │   ├── job.c
│   │   │   ├── makefile
│   │   │   ├── makefile_standalone
│   │   │   ├── mobility.txt
│   │   │   ├── mobility_parser.c
│   │   │   ├── mobility_parser.h
│   │   │   ├── omg.c
│   │   │   ├── omg.h
│   │   │   ├── omg_constants.h
│   │   │   ├── omg_hashtable.c
│   │   │   ├── omg_hashtable.h
│   │   │   ├── omg_vars.h
│   │   │   ├── rwalk.c
│   │   │   ├── rwalk.h
│   │   │   ├── rwp.c
│   │   │   ├── rwp.h
│   │   │   ├── static.c
│   │   │   ├── static.h
│   │   │   ├── steadystaterwp.c
│   │   │   ├── steadystaterwp.h
│   │   │   ├── trace.c
│   │   │   ├── trace.h
│   │   │   ├── trace_hashtable.c
│   │   │   └── trace_hashtable.h
│   │   ├── OMV
│   │   │   ├── README.txt
│   │   │   ├── blue.png
│   │   │   ├── communicationthread.cpp
│   │   │   ├── communicationthread.h
│   │   │   ├── green.png
│   │   │   ├── jpg.jpeg
│   │   │   ├── mus.png
│   │   │   ├── mywindow.cpp
│   │   │   ├── mywindow.h
│   │   │   ├── new.jpg
│   │   │   ├── new2.jpg
│   │   │   ├── omv.cpp
│   │   │   ├── openglwidget.cpp
│   │   │   ├── openglwidget.h
│   │   │   ├── red.png
│   │   │   ├── structures.h
│   │   │   ├── white.png
│   │   │   └── wow.png
│   │   ├── OPT
│   │   │   ├── README.txt
│   │   │   ├── mac_pcap.h
│   │   │   ├── opt.h
│   │   │   ├── packet-rohc.h
│   │   │   ├── probe.c
│   │   │   └── wireshark_headers.h
│   │   └── OTG
│   │       ├── Doxyfile
│   │       ├── OTGplot
│   │       ├── help_OTGplot.txt
│   │       ├── main.c
│   │       ├── makefile
│   │       ├── otg.c
│   │       ├── otg.h
│   │       ├── otg_config.h
│   │       ├── otg_defs.h
│   │       ├── otg_externs.h
│   │       ├── otg_form.c
│   │       ├── otg_form.h
│   │       ├── otg_kpi.c
│   │       ├── otg_kpi.h
│   │       ├── otg_models.c
│   │       ├── otg_models.h
│   │       ├── otg_rx.c
│   │       ├── otg_rx.h
│   │       ├── otg_rx_socket.c
│   │       ├── otg_rx_socket.h
│   │       ├── otg_tx.c
│   │       ├── otg_tx.h
│   │       ├── otg_tx_socket.c
│   │       ├── otg_tx_socket.h
│   │       ├── otg_vars.h
│   │       └── traffic_config.h
│   ├── X2AP
│   │   ├── CMakeLists.txt
│   │   ├── MESSAGES
│   │   │   ├── ASN1
│   │   │   │   ├── R10
│   │   │   │   │   └── x2ap-10.7.0.asn1
│   │   │   │   ├── R11
│   │   │   │   │   └── x2ap-11.9.0.asn1
│   │   │   │   ├── R12
│   │   │   │   │   └── x2ap-12.8.0.asn1
│   │   │   │   ├── R13
│   │   │   │   │   └── x2ap-13.7.0.asn1
│   │   │   │   ├── R14
│   │   │   │   │   ├── x2ap-14.6.0.asn1
│   │   │   │   │   └── x2ap-14.7.0.asn1
│   │   │   │   ├── R14.5
│   │   │   │   │   └── x2ap-14.5.0.asn1
│   │   │   │   ├── R15
│   │   │   │   │   ├── x2ap-15.1.0.asn1
│   │   │   │   │   ├── x2ap-15.2.0.asn1
│   │   │   │   │   ├── x2ap-15.3.0.asn1
│   │   │   │   │   ├── x2ap-15.6.0.asn1
│   │   │   │   │   └── x2ap-15.6.0.cmake
│   │   │   │   ├── R8
│   │   │   │   │   └── x2ap-8.9.0.asn1
│   │   │   │   └── R9
│   │   │   │       └── x2ap-9.6.0.asn1
│   │   │   └── CMakeLists.txt
│   │   ├── x2ap_common.c
│   │   ├── x2ap_common.h
│   │   ├── x2ap_eNB.c
│   │   ├── x2ap_eNB.h
│   │   ├── x2ap_eNB_decoder.c
│   │   ├── x2ap_eNB_decoder.h
│   │   ├── x2ap_eNB_defs.h
│   │   ├── x2ap_eNB_encoder.c
│   │   ├── x2ap_eNB_encoder.h
│   │   ├── x2ap_eNB_generate_messages.c
│   │   ├── x2ap_eNB_generate_messages.h
│   │   ├── x2ap_eNB_handler.c
│   │   ├── x2ap_eNB_handler.h
│   │   ├── x2ap_eNB_itti_messaging.c
│   │   ├── x2ap_eNB_itti_messaging.h
│   │   ├── x2ap_eNB_management_procedures.c
│   │   ├── x2ap_eNB_management_procedures.h
│   │   ├── x2ap_ids.c
│   │   ├── x2ap_ids.h
│   │   ├── x2ap_timers.c
│   │   └── x2ap_timers.h
│   └── XNAP
│       ├── CMakeLists.txt
│       ├── MESSAGES
│       │   ├── ASN1
│       │   │   ├── xnap_R16.2.0.asn
│       │   │   └── xnap_R16.2.0.cmake
│       │   └── CMakeLists.txt
│       ├── lib
│       │   ├── CMakeLists.txt
│       │   ├── xnap_gNB_interface_management.c
│       │   ├── xnap_gNB_interface_management.h
│       │   ├── xnap_gNB_mobility_management.c
│       │   ├── xnap_gNB_mobility_management.h
│       │   ├── xnap_lib_common.c
│       │   ├── xnap_lib_common.h
│       │   └── xnap_lib_includes.h
│       ├── tests
│       │   ├── CMakeLists.txt
│       │   └── xnap_lib_test.c
│       ├── xnap_common.c
│       └── xnap_common.h
├── openair3
│   ├── CMakeLists.txt
│   ├── COMMON
│   │   ├── common_types.h
│   │   ├── intertask_interface_conf.h
│   │   └── security_types.h
│   ├── DOCS
│   │   ├── Latex
│   │   │   └── DefaultBearer
│   │   │       ├── DefaultBearer.pdf
│   │   │       └── DefaultBearer.tex
│   │   └── Makefile.am
│   ├── LPP
│   │   ├── CMakeLists.txt
│   │   └── MESSAGES
│   │       ├── ASN1
│   │       │   ├── 37355-g60.asn
│   │       │   └── 37355-g60.cmake
│   │       └── CMakeLists.txt
│   ├── M3AP
│   │   ├── CMakeLists.txt
│   │   ├── MESSAGES
│   │   │   ├── ASN1
│   │   │   │   ├── m3ap-14.0.0.asn
│   │   │   │   └── m3ap-14.0.0.cmake
│   │   │   └── CMakeLists.txt
│   │   ├── m3ap_MCE.c
│   │   ├── m3ap_MCE.h
│   │   ├── m3ap_MCE_defs.h
│   │   ├── m3ap_MCE_generate_messages.h
│   │   ├── m3ap_MCE_generate_messsages.c
│   │   ├── m3ap_MCE_handler.c
│   │   ├── m3ap_MCE_handler.h
│   │   ├── m3ap_MCE_interface_management.c
│   │   ├── m3ap_MCE_interface_management.h
│   │   ├── m3ap_MCE_management_procedures.c
│   │   ├── m3ap_MCE_management_procedures.h
│   │   ├── m3ap_MME.c
│   │   ├── m3ap_MME.h
│   │   ├── m3ap_MME_defs.h
│   │   ├── m3ap_MME_generate_messages.c
│   │   ├── m3ap_MME_generate_messages.h
│   │   ├── m3ap_MME_handler.c
│   │   ├── m3ap_MME_handler.h
│   │   ├── m3ap_MME_interface_management.c
│   │   ├── m3ap_MME_interface_management.h
│   │   ├── m3ap_MME_management_procedures.c
│   │   ├── m3ap_MME_management_procedures.h
│   │   ├── m3ap_common.c
│   │   ├── m3ap_common.h
│   │   ├── m3ap_decoder.c
│   │   ├── m3ap_decoder.h
│   │   ├── m3ap_default_values.h
│   │   ├── m3ap_encoder.c
│   │   ├── m3ap_encoder.h
│   │   ├── m3ap_handler.c
│   │   ├── m3ap_handler.h
│   │   ├── m3ap_ids.c
│   │   ├── m3ap_ids.h
│   │   ├── m3ap_itti_messaging.c
│   │   ├── m3ap_itti_messaging.h
│   │   ├── m3ap_timers.c
│   │   └── m3ap_timers.h
│   ├── MME_APP
│   │   ├── mme_app.c
│   │   ├── mme_app.h
│   │   ├── mme_config.c
│   │   └── mme_config.h
│   ├── NAS
│   │   ├── CMakeLists.txt
│   │   ├── COMMON
│   │   │   ├── API
│   │   │   │   └── NETWORK
│   │   │   │       ├── Makefile
│   │   │   │       ├── as_message.c
│   │   │   │       ├── nas_message.c
│   │   │   │       ├── nas_message.h
│   │   │   │       ├── network_api.c
│   │   │   │       └── network_api.h
│   │   │   ├── CMakeLists.txt
│   │   │   ├── EMM
│   │   │   │   ├── CMakeLists.txt
│   │   │   │   └── MSG
│   │   │   │       ├── AttachAccept.c
│   │   │   │       ├── AttachAccept.h
│   │   │   │       ├── AttachComplete.c
│   │   │   │       ├── AttachComplete.h
│   │   │   │       ├── AttachReject.c
│   │   │   │       ├── AttachReject.h
│   │   │   │       ├── AttachRequest.c
│   │   │   │       ├── AttachRequest.h
│   │   │   │       ├── AuthenticationFailure.c
│   │   │   │       ├── AuthenticationFailure.h
│   │   │   │       ├── AuthenticationReject.c
│   │   │   │       ├── AuthenticationReject.h
│   │   │   │       ├── AuthenticationRequest.c
│   │   │   │       ├── AuthenticationRequest.h
│   │   │   │       ├── AuthenticationResponse.c
│   │   │   │       ├── AuthenticationResponse.h
│   │   │   │       ├── CsServiceNotification.c
│   │   │   │       ├── CsServiceNotification.h
│   │   │   │       ├── DetachAccept.c
│   │   │   │       ├── DetachAccept.h
│   │   │   │       ├── DetachRequest.c
│   │   │   │       ├── DetachRequest.h
│   │   │   │       ├── DownlinkNasTransport.c
│   │   │   │       ├── DownlinkNasTransport.h
│   │   │   │       ├── EmmInformation.c
│   │   │   │       ├── EmmInformation.h
│   │   │   │       ├── EmmStatus.c
│   │   │   │       ├── EmmStatus.h
│   │   │   │       ├── ExtendedServiceRequest.c
│   │   │   │       ├── ExtendedServiceRequest.h
│   │   │   │       ├── GutiReallocationCommand.c
│   │   │   │       ├── GutiReallocationCommand.h
│   │   │   │       ├── GutiReallocationComplete.c
│   │   │   │       ├── GutiReallocationComplete.h
│   │   │   │       ├── IdentityRequest.c
│   │   │   │       ├── IdentityRequest.h
│   │   │   │       ├── IdentityResponse.c
│   │   │   │       ├── IdentityResponse.h
│   │   │   │       ├── Makefile
│   │   │   │       ├── NASSecurityModeCommand.h
│   │   │   │       ├── NASSecurityModeComplete.h
│   │   │   │       ├── SecurityModeCommand.c
│   │   │   │       ├── SecurityModeComplete.c
│   │   │   │       ├── SecurityModeReject.c
│   │   │   │       ├── SecurityModeReject.h
│   │   │   │       ├── ServiceReject.c
│   │   │   │       ├── ServiceReject.h
│   │   │   │       ├── ServiceRequest.c
│   │   │   │       ├── ServiceRequest.h
│   │   │   │       ├── TrackingAreaUpdateAccept.c
│   │   │   │       ├── TrackingAreaUpdateAccept.h
│   │   │   │       ├── TrackingAreaUpdateComplete.c
│   │   │   │       ├── TrackingAreaUpdateComplete.h
│   │   │   │       ├── TrackingAreaUpdateReject.c
│   │   │   │       ├── TrackingAreaUpdateReject.h
│   │   │   │       ├── TrackingAreaUpdateRequest.c
│   │   │   │       ├── TrackingAreaUpdateRequest.h
│   │   │   │       ├── UplinkNasTransport.c
│   │   │   │       ├── UplinkNasTransport.h
│   │   │   │       ├── emm_cause.h
│   │   │   │       ├── emm_msg.c
│   │   │   │       ├── emm_msg.h
│   │   │   │       └── emm_msgDef.h
│   │   │   ├── ESM
│   │   │   │   └── MSG
│   │   │   │       ├── ActivateDedicatedEpsBearerContextAccept.c
│   │   │   │       ├── ActivateDedicatedEpsBearerContextAccept.h
│   │   │   │       ├── ActivateDedicatedEpsBearerContextReject.c
│   │   │   │       ├── ActivateDedicatedEpsBearerContextReject.h
│   │   │   │       ├── ActivateDedicatedEpsBearerContextRequest.c
│   │   │   │       ├── ActivateDedicatedEpsBearerContextRequest.h
│   │   │   │       ├── ActivateDefaultEpsBearerContextAccept.c
│   │   │   │       ├── ActivateDefaultEpsBearerContextAccept.h
│   │   │   │       ├── ActivateDefaultEpsBearerContextReject.c
│   │   │   │       ├── ActivateDefaultEpsBearerContextReject.h
│   │   │   │       ├── ActivateDefaultEpsBearerContextRequest.c
│   │   │   │       ├── ActivateDefaultEpsBearerContextRequest.h
│   │   │   │       ├── BearerResourceAllocationReject.c
│   │   │   │       ├── BearerResourceAllocationReject.h
│   │   │   │       ├── BearerResourceAllocationRequest.c
│   │   │   │       ├── BearerResourceAllocationRequest.h
│   │   │   │       ├── BearerResourceModificationReject.c
│   │   │   │       ├── BearerResourceModificationReject.h
│   │   │   │       ├── BearerResourceModificationRequest.c
│   │   │   │       ├── BearerResourceModificationRequest.h
│   │   │   │       ├── DeactivateEpsBearerContextAccept.c
│   │   │   │       ├── DeactivateEpsBearerContextAccept.h
│   │   │   │       ├── DeactivateEpsBearerContextRequest.c
│   │   │   │       ├── DeactivateEpsBearerContextRequest.h
│   │   │   │       ├── EsmInformationRequest.c
│   │   │   │       ├── EsmInformationRequest.h
│   │   │   │       ├── EsmInformationResponse.c
│   │   │   │       ├── EsmInformationResponse.h
│   │   │   │       ├── EsmStatus.c
│   │   │   │       ├── EsmStatus.h
│   │   │   │       ├── Makefile
│   │   │   │       ├── ModifyEpsBearerContextAccept.c
│   │   │   │       ├── ModifyEpsBearerContextAccept.h
│   │   │   │       ├── ModifyEpsBearerContextReject.c
│   │   │   │       ├── ModifyEpsBearerContextReject.h
│   │   │   │       ├── ModifyEpsBearerContextRequest.c
│   │   │   │       ├── ModifyEpsBearerContextRequest.h
│   │   │   │       ├── PdnConnectivityReject.c
│   │   │   │       ├── PdnConnectivityReject.h
│   │   │   │       ├── PdnConnectivityRequest.c
│   │   │   │       ├── PdnConnectivityRequest.h
│   │   │   │       ├── PdnDisconnectReject.c
│   │   │   │       ├── PdnDisconnectReject.h
│   │   │   │       ├── PdnDisconnectRequest.c
│   │   │   │       ├── PdnDisconnectRequest.h
│   │   │   │       ├── esm_cause.h
│   │   │   │       ├── esm_msg.c
│   │   │   │       ├── esm_msg.h
│   │   │   │       └── esm_msgDef.h
│   │   │   ├── IES
│   │   │   │   ├── AccessPointName.c
│   │   │   │   ├── AccessPointName.h
│   │   │   │   ├── AdditionalUpdateResult.c
│   │   │   │   ├── AdditionalUpdateResult.h
│   │   │   │   ├── AdditionalUpdateType.c
│   │   │   │   ├── AdditionalUpdateType.h
│   │   │   │   ├── ApnAggregateMaximumBitRate.c
│   │   │   │   ├── ApnAggregateMaximumBitRate.h
│   │   │   │   ├── AuthenticationFailureParameter.c
│   │   │   │   ├── AuthenticationFailureParameter.h
│   │   │   │   ├── AuthenticationParameterAutn.c
│   │   │   │   ├── AuthenticationParameterAutn.h
│   │   │   │   ├── AuthenticationParameterRand.c
│   │   │   │   ├── AuthenticationParameterRand.h
│   │   │   │   ├── AuthenticationResponseParameter.c
│   │   │   │   ├── AuthenticationResponseParameter.h
│   │   │   │   ├── CMakeLists.txt
│   │   │   │   ├── CipheringKeySequenceNumber.c
│   │   │   │   ├── CipheringKeySequenceNumber.h
│   │   │   │   ├── Cli.c
│   │   │   │   ├── Cli.h
│   │   │   │   ├── CsfbResponse.c
│   │   │   │   ├── CsfbResponse.h
│   │   │   │   ├── DaylightSavingTime.c
│   │   │   │   ├── DaylightSavingTime.h
│   │   │   │   ├── DetachType.c
│   │   │   │   ├── DetachType.h
│   │   │   │   ├── DrxParameter.c
│   │   │   │   ├── DrxParameter.h
│   │   │   │   ├── EmergencyNumberList.c
│   │   │   │   ├── EmergencyNumberList.h
│   │   │   │   ├── EmmCause.c
│   │   │   │   ├── EmmCause.h
│   │   │   │   ├── EpsAttachResult.c
│   │   │   │   ├── EpsAttachResult.h
│   │   │   │   ├── EpsAttachType.c
│   │   │   │   ├── EpsAttachType.h
│   │   │   │   ├── EpsBearerContextStatus.c
│   │   │   │   ├── EpsBearerContextStatus.h
│   │   │   │   ├── EpsBearerIdentity.c
│   │   │   │   ├── EpsBearerIdentity.h
│   │   │   │   ├── EpsMobileIdentity.c
│   │   │   │   ├── EpsMobileIdentity.h
│   │   │   │   ├── EpsNetworkFeatureSupport.c
│   │   │   │   ├── EpsNetworkFeatureSupport.h
│   │   │   │   ├── EpsQualityOfService.c
│   │   │   │   ├── EpsQualityOfService.h
│   │   │   │   ├── EpsUpdateResult.c
│   │   │   │   ├── EpsUpdateResult.h
│   │   │   │   ├── EpsUpdateType.c
│   │   │   │   ├── EpsUpdateType.h
│   │   │   │   ├── EsmCause.c
│   │   │   │   ├── EsmCause.h
│   │   │   │   ├── EsmInformationTransferFlag.c
│   │   │   │   ├── EsmInformationTransferFlag.h
│   │   │   │   ├── EsmMessageContainer.c
│   │   │   │   ├── EsmMessageContainer.h
│   │   │   │   ├── GprsTimer.c
│   │   │   │   ├── GprsTimer.h
│   │   │   │   ├── GutiType.c
│   │   │   │   ├── GutiType.h
│   │   │   │   ├── IdentityType2.c
│   │   │   │   ├── IdentityType2.h
│   │   │   │   ├── ImeisvRequest.c
│   │   │   │   ├── ImeisvRequest.h
│   │   │   │   ├── KsiAndSequenceNumber.c
│   │   │   │   ├── KsiAndSequenceNumber.h
│   │   │   │   ├── LcsClientIdentity.c
│   │   │   │   ├── LcsClientIdentity.h
│   │   │   │   ├── LcsIndicator.c
│   │   │   │   ├── LcsIndicator.h
│   │   │   │   ├── LinkedEpsBearerIdentity.c
│   │   │   │   ├── LinkedEpsBearerIdentity.h
│   │   │   │   ├── LlcServiceAccessPointIdentifier.c
│   │   │   │   ├── LlcServiceAccessPointIdentifier.h
│   │   │   │   ├── LocationAreaIdentification.c
│   │   │   │   ├── LocationAreaIdentification.h
│   │   │   │   ├── Makefile
│   │   │   │   ├── MessageType.c
│   │   │   │   ├── MessageType.h
│   │   │   │   ├── MobileIdentity.c
│   │   │   │   ├── MobileIdentity.h
│   │   │   │   ├── MobileStationClassmark2.c
│   │   │   │   ├── MobileStationClassmark2.h
│   │   │   │   ├── MobileStationClassmark3.c
│   │   │   │   ├── MobileStationClassmark3.h
│   │   │   │   ├── MsNetworkCapability.c
│   │   │   │   ├── MsNetworkCapability.h
│   │   │   │   ├── MsNetworkFeatureSupport.c
│   │   │   │   ├── MsNetworkFeatureSupport.h
│   │   │   │   ├── NasKeySetIdentifier.c
│   │   │   │   ├── NasKeySetIdentifier.h
│   │   │   │   ├── NasMessageContainer.c
│   │   │   │   ├── NasMessageContainer.h
│   │   │   │   ├── NasPagingIdentity.h
│   │   │   │   ├── NasRequestType.c
│   │   │   │   ├── NasRequestType.h
│   │   │   │   ├── NasSecurityAlgorithms.c
│   │   │   │   ├── NasSecurityAlgorithms.h
│   │   │   │   ├── NetworkName.c
│   │   │   │   ├── NetworkName.h
│   │   │   │   ├── Nonce.c
│   │   │   │   ├── Nonce.h
│   │   │   │   ├── PTmsiSignature.c
│   │   │   │   ├── PTmsiSignature.h
│   │   │   │   ├── PacketFlowIdentifier.c
│   │   │   │   ├── PacketFlowIdentifier.h
│   │   │   │   ├── PagingIdentity.c
│   │   │   │   ├── PagingIdentity.h
│   │   │   │   ├── PdnAddress.c
│   │   │   │   ├── PdnAddress.h
│   │   │   │   ├── PdnType.c
│   │   │   │   ├── PdnType.h
│   │   │   │   ├── PlmnList.c
│   │   │   │   ├── PlmnList.h
│   │   │   │   ├── ProcedureTransactionIdentity.c
│   │   │   │   ├── ProcedureTransactionIdentity.h
│   │   │   │   ├── ProtocolConfigurationOptions.c
│   │   │   │   ├── ProtocolConfigurationOptions.h
│   │   │   │   ├── ProtocolDiscriminator.c
│   │   │   │   ├── ProtocolDiscriminator.h
│   │   │   │   ├── QualityOfService.c
│   │   │   │   ├── QualityOfService.h
│   │   │   │   ├── RadioPriority.c
│   │   │   │   ├── RadioPriority.h
│   │   │   │   ├── SecurityHeaderType.c
│   │   │   │   ├── SecurityHeaderType.h
│   │   │   │   ├── ServiceType.c
│   │   │   │   ├── ServiceType.h
│   │   │   │   ├── ShortMac.c
│   │   │   │   ├── ShortMac.h
│   │   │   │   ├── SsCode.c
│   │   │   │   ├── SsCode.h
│   │   │   │   ├── SupportedCodecList.c
│   │   │   │   ├── SupportedCodecList.h
│   │   │   │   ├── TimeZone.c
│   │   │   │   ├── TimeZone.h
│   │   │   │   ├── TimeZoneAndTime.c
│   │   │   │   ├── TimeZoneAndTime.h
│   │   │   │   ├── TmsiStatus.c
│   │   │   │   ├── TmsiStatus.h
│   │   │   │   ├── TrackingAreaIdentity.c
│   │   │   │   ├── TrackingAreaIdentity.h
│   │   │   │   ├── TrackingAreaIdentityList.c
│   │   │   │   ├── TrackingAreaIdentityList.h
│   │   │   │   ├── TrafficFlowAggregateDescription.c
│   │   │   │   ├── TrafficFlowAggregateDescription.h
│   │   │   │   ├── TrafficFlowTemplate.c
│   │   │   │   ├── TrafficFlowTemplate.h
│   │   │   │   ├── TransactionIdentifier.c
│   │   │   │   ├── TransactionIdentifier.h
│   │   │   │   ├── UeNetworkCapability.c
│   │   │   │   ├── UeNetworkCapability.h
│   │   │   │   ├── UeRadioCapabilityInformationUpdateNeeded.c
│   │   │   │   ├── UeRadioCapabilityInformationUpdateNeeded.h
│   │   │   │   ├── UeSecurityCapability.c
│   │   │   │   ├── UeSecurityCapability.h
│   │   │   │   ├── VoiceDomainPreferenceAndUeUsageSetting.c
│   │   │   │   └── VoiceDomainPreferenceAndUeUsageSetting.h
│   │   │   ├── UTIL
│   │   │   │   ├── CMakeLists.txt
│   │   │   │   ├── Makefile
│   │   │   │   ├── OctetString.c
│   │   │   │   ├── OctetString.h
│   │   │   │   ├── TLVDecoder.c
│   │   │   │   ├── TLVDecoder.h
│   │   │   │   ├── TLVEncoder.h
│   │   │   │   ├── device.c
│   │   │   │   ├── device.h
│   │   │   │   ├── nas_log.h
│   │   │   │   ├── nas_timer.c
│   │   │   │   ├── nas_timer.h
│   │   │   │   ├── parser.c
│   │   │   │   ├── parser.h
│   │   │   │   ├── socket.c
│   │   │   │   ├── socket.h
│   │   │   │   ├── stty.c
│   │   │   │   └── tst
│   │   │   │       ├── Makefile
│   │   │   │       ├── timer.c
│   │   │   │       └── timer_debug.txt
│   │   │   ├── milenage.h
│   │   │   ├── securityDef.h
│   │   │   └── userDef.h
│   │   ├── NR_UE
│   │   │   ├── 5GS
│   │   │   │   ├── 5GMM
│   │   │   │   │   ├── IES
│   │   │   │   │   │   ├── CMakeLists.txt
│   │   │   │   │   │   ├── FGCNasMessageContainer.c
│   │   │   │   │   │   ├── FGCNasMessageContainer.h
│   │   │   │   │   │   ├── FGMMCapability.c
│   │   │   │   │   │   ├── FGMMCapability.h
│   │   │   │   │   │   ├── FGSDeregistrationType.h
│   │   │   │   │   │   ├── FGSMobileIdentity.c
│   │   │   │   │   │   ├── FGSMobileIdentity.h
│   │   │   │   │   │   ├── FGSRegistrationType.c
│   │   │   │   │   │   ├── FGSRegistrationType.h
│   │   │   │   │   │   ├── NrUESecurityCapability.c
│   │   │   │   │   │   ├── NrUESecurityCapability.h
│   │   │   │   │   │   ├── SORTransparentContainer.c
│   │   │   │   │   │   └── SORTransparentContainer.h
│   │   │   │   │   └── MSG
│   │   │   │   │       ├── CMakeLists.txt
│   │   │   │   │       ├── FGSAuthenticationResponse.c
│   │   │   │   │       ├── FGSAuthenticationResponse.h
│   │   │   │   │       ├── FGSDeregistrationRequestUEOriginating.c
│   │   │   │   │       ├── FGSDeregistrationRequestUEOriginating.h
│   │   │   │   │       ├── FGSIdentityResponse.c
│   │   │   │   │       ├── FGSIdentityResponse.h
│   │   │   │   │       ├── FGSNASSecurityModeComplete.c
│   │   │   │   │       ├── FGSNASSecurityModeComplete.h
│   │   │   │   │       ├── FGSNASSecurityModeReject.c
│   │   │   │   │       ├── FGSNASSecurityModeReject.h
│   │   │   │   │       ├── FGSUplinkNasTransport.c
│   │   │   │   │       ├── FGSUplinkNasTransport.h
│   │   │   │   │       ├── RegistrationAccept.c
│   │   │   │   │       ├── RegistrationAccept.h
│   │   │   │   │       ├── RegistrationComplete.c
│   │   │   │   │       ├── RegistrationComplete.h
│   │   │   │   │       ├── RegistrationRequest.c
│   │   │   │   │       ├── RegistrationRequest.h
│   │   │   │   │       ├── fgmm_authentication_failure.c
│   │   │   │   │       ├── fgmm_authentication_failure.h
│   │   │   │   │       ├── fgmm_authentication_reject.c
│   │   │   │   │       ├── fgmm_authentication_reject.h
│   │   │   │   │       ├── fgmm_authentication_request.h
│   │   │   │   │       ├── fgmm_identity_request.c
│   │   │   │   │       ├── fgmm_identity_request.h
│   │   │   │   │       ├── fgmm_lib.c
│   │   │   │   │       ├── fgmm_lib.h
│   │   │   │   │       ├── fgmm_service_accept.c
│   │   │   │   │       ├── fgmm_service_accept.h
│   │   │   │   │       ├── fgmm_service_reject.c
│   │   │   │   │       ├── fgmm_service_reject.h
│   │   │   │   │       ├── fgs_service_request.c
│   │   │   │   │       └── fgs_service_request.h
│   │   │   │   ├── 5GSM
│   │   │   │   │   └── MSG
│   │   │   │   │       ├── CMakeLists.txt
│   │   │   │   │       ├── PduSessionEstablishRequest.c
│   │   │   │   │       ├── PduSessionEstablishRequest.h
│   │   │   │   │       ├── PduSessionEstablishmentAccept.c
│   │   │   │   │       └── PduSessionEstablishmentAccept.h
│   │   │   │   ├── CMakeLists.txt
│   │   │   │   ├── NR_NAS_defs.h
│   │   │   │   ├── fgs_nas_lib.c
│   │   │   │   ├── fgs_nas_utils.h
│   │   │   │   └── tests
│   │   │   │       ├── CMakeLists.txt
│   │   │   │       └── nas_lib_test.c
│   │   │   ├── CMakeLists.txt
│   │   │   ├── nr_nas_msg.c
│   │   │   └── nr_nas_msg.h
│   │   ├── TEST
│   │   │   ├── AS_SIMULATOR
│   │   │   │   ├── Makefile
│   │   │   │   ├── as_data.c
│   │   │   │   ├── as_data.h
│   │   │   │   ├── as_process.c
│   │   │   │   ├── as_process.h
│   │   │   │   ├── as_simulator.c
│   │   │   │   ├── as_simulator_parser.c
│   │   │   │   ├── as_simulator_parser.h
│   │   │   │   ├── nas_data.c
│   │   │   │   ├── nas_data.h
│   │   │   │   ├── nas_process.c
│   │   │   │   └── nas_process.h
│   │   │   ├── NETWORK
│   │   │   │   ├── Makefile
│   │   │   │   ├── README
│   │   │   │   ├── network_parser.c
│   │   │   │   ├── network_parser.h
│   │   │   │   └── network_simulator.c
│   │   │   └── USER
│   │   │       ├── Makefile
│   │   │       ├── user_parser.c
│   │   │       ├── user_parser.h
│   │   │       └── user_simulator.c
│   │   ├── TOOLS
│   │   │   ├── CMakeLists.txt
│   │   │   ├── conf2uedata.c
│   │   │   ├── conf2uedata.h
│   │   │   ├── conf_emm.c
│   │   │   ├── conf_emm.h
│   │   │   ├── conf_network.c
│   │   │   ├── conf_network.h
│   │   │   ├── conf_parser.c
│   │   │   ├── conf_parser.h
│   │   │   ├── conf_user_data.c
│   │   │   ├── conf_user_data.h
│   │   │   ├── conf_user_plmn.c
│   │   │   ├── conf_user_plmn.h
│   │   │   ├── conf_usim.c
│   │   │   ├── conf_usim.h
│   │   │   ├── display.c
│   │   │   ├── display.h
│   │   │   ├── fs.c
│   │   │   ├── fs.h
│   │   │   ├── nvram.c
│   │   │   ├── ue_bcom_test.conf
│   │   │   ├── ue_eurecom_test_sfr.conf
│   │   │   ├── ue_tcl_test.conf
│   │   │   └── usim.c
│   │   └── UE
│   │       ├── API
│   │       │   ├── CMakeLists.txt
│   │       │   ├── USER
│   │       │   │   ├── at_command.c
│   │       │   │   ├── at_command.h
│   │       │   │   ├── at_error.c
│   │       │   │   ├── at_error.h
│   │       │   │   ├── at_response.c
│   │       │   │   ├── at_response.h
│   │       │   │   ├── tst
│   │       │   │   │   ├── at_parser.c
│   │       │   │   │   ├── at_parser.in
│   │       │   │   │   ├── at_parser.in.bis
│   │       │   │   │   ├── at_parser.out
│   │       │   │   │   ├── at_parser.out.bis
│   │       │   │   │   └── smartcom.txt
│   │       │   │   ├── user_api.c
│   │       │   │   ├── user_api.h
│   │       │   │   ├── user_api_defs.h
│   │       │   │   ├── user_indication.c
│   │       │   │   └── user_indication.h
│   │       │   └── USIM
│   │       │       ├── CMakeLists.txt
│   │       │       ├── aka_functions.c
│   │       │       ├── aka_functions.h
│   │       │       ├── usim_api.c
│   │       │       └── usim_api.h
│   │       ├── CMakeLists.txt
│   │       ├── EMM
│   │       │   ├── Attach.c
│   │       │   ├── Authentication.c
│   │       │   ├── Authentication.h
│   │       │   ├── Detach.c
│   │       │   ├── EmmStatusHdl.c
│   │       │   ├── Identification.c
│   │       │   ├── IdleMode.c
│   │       │   ├── IdleMode.h
│   │       │   ├── IdleMode_defs.h
│   │       │   ├── LowerLayer.c
│   │       │   ├── LowerLayer.h
│   │       │   ├── LowerLayer_defs.h
│   │       │   ├── SAP
│   │       │   │   ├── EmmDeregistered.c
│   │       │   │   ├── EmmDeregisteredAttachNeeded.c
│   │       │   │   ├── EmmDeregisteredAttemptingToAttach.c
│   │       │   │   ├── EmmDeregisteredInitiated.c
│   │       │   │   ├── EmmDeregisteredLimitedService.c
│   │       │   │   ├── EmmDeregisteredNoCellAvailable.c
│   │       │   │   ├── EmmDeregisteredNoImsi.c
│   │       │   │   ├── EmmDeregisteredNormalService.c
│   │       │   │   ├── EmmDeregisteredPlmnSearch.c
│   │       │   │   ├── EmmNull.c
│   │       │   │   ├── EmmRegistered.c
│   │       │   │   ├── EmmRegisteredAttemptingToUpdate.c
│   │       │   │   ├── EmmRegisteredImsiDetachInitiated.c
│   │       │   │   ├── EmmRegisteredInitiated.c
│   │       │   │   ├── EmmRegisteredLimitedService.c
│   │       │   │   ├── EmmRegisteredNoCellAvailable.c
│   │       │   │   ├── EmmRegisteredNormalService.c
│   │       │   │   ├── EmmRegisteredPlmnSearch.c
│   │       │   │   ├── EmmRegisteredUpdateNeeded.c
│   │       │   │   ├── EmmServiceRequestInitiated.c
│   │       │   │   ├── EmmTrackingAreaUpdatingInitiated.c
│   │       │   │   ├── emm_as.c
│   │       │   │   ├── emm_as.h
│   │       │   │   ├── emm_asDef.h
│   │       │   │   ├── emm_esm.c
│   │       │   │   ├── emm_esm.h
│   │       │   │   ├── emm_esmDef.h
│   │       │   │   ├── emm_fsm.c
│   │       │   │   ├── emm_fsm.h
│   │       │   │   ├── emm_recv.c
│   │       │   │   ├── emm_recv.h
│   │       │   │   ├── emm_reg.c
│   │       │   │   ├── emm_reg.h
│   │       │   │   ├── emm_regDef.h
│   │       │   │   ├── emm_sap.c
│   │       │   │   ├── emm_sap.h
│   │       │   │   ├── emm_send.c
│   │       │   │   └── emm_send.h
│   │       │   ├── SecurityModeControl.c
│   │       │   ├── SecurityModeControl.h
│   │       │   ├── ServiceRequestHdl.c
│   │       │   ├── TrackingAreaUpdate.c
│   │       │   ├── emmData.h
│   │       │   ├── emm_fsm_defs.h
│   │       │   ├── emm_main.c
│   │       │   ├── emm_main.h
│   │       │   ├── emm_proc.h
│   │       │   ├── emm_proc_defs.h
│   │       │   └── emm_timers.h
│   │       ├── ESM
│   │       │   ├── DedicatedEpsBearerContextActivation.c
│   │       │   ├── DefaultEpsBearerContextActivation.c
│   │       │   ├── EpsBearerContextDeactivation.c
│   │       │   ├── EsmStatusHdl.c
│   │       │   ├── PdnConnectivity.c
│   │       │   ├── PdnDisconnect.c
│   │       │   ├── SAP
│   │       │   │   ├── esm_recv.c
│   │       │   │   ├── esm_recv.h
│   │       │   │   ├── esm_sap.c
│   │       │   │   ├── esm_sap.h
│   │       │   │   ├── esm_sapDef.h
│   │       │   │   ├── esm_send.c
│   │       │   │   └── esm_send.h
│   │       │   ├── esmData.h
│   │       │   ├── esm_ebr.c
│   │       │   ├── esm_ebr.h
│   │       │   ├── esm_ebr_context.c
│   │       │   ├── esm_ebr_context.h
│   │       │   ├── esm_ip.c
│   │       │   ├── esm_main.c
│   │       │   ├── esm_main.h
│   │       │   ├── esm_proc.h
│   │       │   ├── esm_pt.c
│   │       │   ├── esm_pt.h
│   │       │   └── esm_pt_defs.h
│   │       ├── UEprocess.c
│   │       ├── nas_itti_messaging.c
│   │       ├── nas_itti_messaging.h
│   │       ├── nas_network.c
│   │       ├── nas_network.h
│   │       ├── nas_parser.c
│   │       ├── nas_parser.h
│   │       ├── nas_proc.c
│   │       ├── nas_proc.h
│   │       ├── nas_proc_defs.h
│   │       ├── nas_ue_task.c
│   │       ├── nas_ue_task.h
│   │       ├── nas_user.c
│   │       ├── nas_user.h
│   │       └── user_defs.h
│   ├── NGAP
│   │   ├── CMakeLists.txt
│   │   ├── MESSAGES
│   │   │   ├── ASN1
│   │   │   │   ├── ngap-15.8.0.asn1
│   │   │   │   └── ngap-15.8.0.cmake
│   │   │   └── CMakeLists.txt
│   │   ├── ngap_common.c
│   │   ├── ngap_common.h
│   │   ├── ngap_gNB.c
│   │   ├── ngap_gNB.h
│   │   ├── ngap_gNB_NRPPa_transport_procedures.c
│   │   ├── ngap_gNB_NRPPa_transport_procedures.h
│   │   ├── ngap_gNB_context_management_procedures.c
│   │   ├── ngap_gNB_context_management_procedures.h
│   │   ├── ngap_gNB_decoder.c
│   │   ├── ngap_gNB_decoder.h
│   │   ├── ngap_gNB_default_values.h
│   │   ├── ngap_gNB_defs.h
│   │   ├── ngap_gNB_encoder.c
│   │   ├── ngap_gNB_encoder.h
│   │   ├── ngap_gNB_handlers.c
│   │   ├── ngap_gNB_handlers.h
│   │   ├── ngap_gNB_itti_messaging.c
│   │   ├── ngap_gNB_itti_messaging.h
│   │   ├── ngap_gNB_management_procedures.c
│   │   ├── ngap_gNB_management_procedures.h
│   │   ├── ngap_gNB_mobility_management.c
│   │   ├── ngap_gNB_mobility_management.h
│   │   ├── ngap_gNB_nas_procedures.c
│   │   ├── ngap_gNB_nas_procedures.h
│   │   ├── ngap_gNB_nnsf.c
│   │   ├── ngap_gNB_nnsf.h
│   │   ├── ngap_gNB_overload.c
│   │   ├── ngap_gNB_overload.h
│   │   ├── ngap_gNB_paging.c
│   │   ├── ngap_gNB_paging.h
│   │   ├── ngap_gNB_pdu_session_management.c
│   │   ├── ngap_gNB_pdu_session_management.h
│   │   ├── ngap_gNB_ue_context.c
│   │   ├── ngap_gNB_ue_context.h
│   │   ├── ngap_msg_includes.h
│   │   ├── ngap_utils.h
│   │   └── tests
│   │       ├── CMakeLists.txt
│   │       └── ngap_lib_test.c
│   ├── NRPPA
│   │   ├── CMakeLists.txt
│   │   ├── MESSAGES
│   │   │   ├── ASN1
│   │   │   │   ├── 38455.asn
│   │   │   │   └── 38455.cmake
│   │   │   └── CMakeLists.txt
│   │   ├── nrppa_common.h
│   │   ├── nrppa_gNB.c
│   │   ├── nrppa_gNB.h
│   │   ├── nrppa_gNB_config.c
│   │   ├── nrppa_gNB_config.h
│   │   ├── nrppa_gNB_decoder.c
│   │   ├── nrppa_gNB_decoder.h
│   │   ├── nrppa_gNB_encoder.c
│   │   ├── nrppa_gNB_encoder.h
│   │   ├── nrppa_gNB_handlers.c
│   │   ├── nrppa_gNB_handlers.h
│   │   ├── nrppa_gNB_location_information_transfer.c
│   │   ├── nrppa_gNB_location_information_transfer.h
│   │   ├── nrppa_gNB_measurement_information_transfer.c
│   │   ├── nrppa_gNB_measurement_information_transfer.h
│   │   ├── nrppa_gNB_ue_context.c
│   │   ├── nrppa_gNB_ue_context.h
│   │   ├── nrppa_includes.h
│   │   └── test_nrppa.c
│   ├── S1AP
│   │   ├── CMakeLists.txt
│   │   ├── MESSAGES
│   │   │   ├── ASN1
│   │   │   │   ├── R10
│   │   │   │   │   └── s1ap-10.9.0.asn1
│   │   │   │   ├── R11
│   │   │   │   │   └── s1ap-11.8.0.asn1
│   │   │   │   ├── R12
│   │   │   │   │   └── s1ap-12.7.0.asn1
│   │   │   │   ├── R13
│   │   │   │   │   └── s1ap-13.6.0.asn1
│   │   │   │   ├── R14
│   │   │   │   │   ├── s1ap-14.5.0.asn1
│   │   │   │   │   ├── s1ap-14.6.0.asn1
│   │   │   │   │   └── s1ap-14.7.0.asn1
│   │   │   │   ├── R14.4
│   │   │   │   │   └── s1ap-14.4.0.asn1
│   │   │   │   ├── R15
│   │   │   │   │   ├── s1ap-15.1.0.asn1
│   │   │   │   │   ├── s1ap-15.2.0.asn1
│   │   │   │   │   ├── s1ap-15.3.0.asn1
│   │   │   │   │   ├── s1ap-15.6.0.asn1
│   │   │   │   │   └── s1ap-15.6.0.cmake
│   │   │   │   ├── R8
│   │   │   │   │   └── s1ap-8.10.0.asn1
│   │   │   │   ├── R9
│   │   │   │   │   └── s1ap-9.10.0.asn1
│   │   │   │   └── README
│   │   │   └── CMakeLists.txt
│   │   ├── s1ap_common.h
│   │   ├── s1ap_eNB.c
│   │   ├── s1ap_eNB.h
│   │   ├── s1ap_eNB_context_management_procedures.c
│   │   ├── s1ap_eNB_context_management_procedures.h
│   │   ├── s1ap_eNB_decoder.c
│   │   ├── s1ap_eNB_decoder.h
│   │   ├── s1ap_eNB_default_values.h
│   │   ├── s1ap_eNB_defs.h
│   │   ├── s1ap_eNB_encoder.c
│   │   ├── s1ap_eNB_encoder.h
│   │   ├── s1ap_eNB_handlers.c
│   │   ├── s1ap_eNB_handlers.h
│   │   ├── s1ap_eNB_itti_messaging.c
│   │   ├── s1ap_eNB_itti_messaging.h
│   │   ├── s1ap_eNB_management_procedures.c
│   │   ├── s1ap_eNB_management_procedures.h
│   │   ├── s1ap_eNB_nas_procedures.c
│   │   ├── s1ap_eNB_nas_procedures.h
│   │   ├── s1ap_eNB_nnsf.c
│   │   ├── s1ap_eNB_nnsf.h
│   │   ├── s1ap_eNB_overload.c
│   │   ├── s1ap_eNB_overload.h
│   │   ├── s1ap_eNB_trace.c
│   │   ├── s1ap_eNB_trace.h
│   │   ├── s1ap_eNB_ue_context.c
│   │   └── s1ap_eNB_ue_context.h
│   ├── SCTP
│   │   ├── sctp_common.c
│   │   ├── sctp_common.h
│   │   ├── sctp_default_values.h
│   │   ├── sctp_eNB_defs.h
│   │   ├── sctp_eNB_itti_messaging.c
│   │   ├── sctp_eNB_itti_messaging.h
│   │   ├── sctp_eNB_task.c
│   │   └── sctp_eNB_task.h
│   ├── SECU
│   │   ├── aes_128.h
│   │   ├── aes_128_cbc_cmac.c
│   │   ├── aes_128_cbc_cmac.h
│   │   ├── aes_128_ctr.c
│   │   ├── aes_128_ctr.h
│   │   ├── aes_128_ecb.c
│   │   ├── aes_128_ecb.h
│   │   ├── curve_25519.c
│   │   ├── curve_25519.h
│   │   ├── kdf.c
│   │   ├── kdf.h
│   │   ├── key_nas_deriver.c
│   │   ├── key_nas_deriver.h
│   │   ├── nas_stream_eea0.c
│   │   ├── nas_stream_eea0.h
│   │   ├── nas_stream_eea1.c
│   │   ├── nas_stream_eea1.h
│   │   ├── nas_stream_eea2.c
│   │   ├── nas_stream_eea2.h
│   │   ├── nas_stream_eia1.c
│   │   ├── nas_stream_eia1.h
│   │   ├── nas_stream_eia2.c
│   │   ├── nas_stream_eia2.h
│   │   ├── rijndael.c
│   │   ├── rijndael.h
│   │   ├── secu_defs.c
│   │   ├── secu_defs.h
│   │   ├── sha_256_hmac.c
│   │   ├── sha_256_hmac.h
│   │   ├── snow3g.c
│   │   ├── snow3g.h
│   │   ├── x963_kdf.c
│   │   └── x963_kdf.h
│   ├── TEST
│   │   ├── Makefile.am
│   │   ├── test_aes128_cmac_encrypt.c
│   │   ├── test_aes128_ctr.c
│   │   ├── test_kdf.c
│   │   ├── test_s1ap.c
│   │   ├── test_secu.c
│   │   ├── test_secu_kenb.c
│   │   ├── test_secu_knas.c
│   │   ├── test_secu_knas_encrypt_eea1.c
│   │   ├── test_secu_knas_encrypt_eea2.c
│   │   ├── test_secu_knas_encrypt_eia1.c
│   │   ├── test_secu_knas_encrypt_eia2.c
│   │   └── test_secu_knas_stream_int.c
│   ├── UICC
│   │   ├── CMakeLists.txt
│   │   ├── pdu_session.c
│   │   ├── pdu_session.h
│   │   ├── usim_interface.c
│   │   └── usim_interface.h
│   ├── UTILS
│   │   └── conversions.h
│   └── ocp-gtpu
│       ├── CMakeLists.txt
│       ├── gtp_itf.cpp
│       ├── gtp_itf.h
│       ├── gtpu_extensions.c
│       ├── gtpu_extensions.h
│       └── tests
│           ├── CMakeLists.txt
│           └── test_gtp.cpp
├── openshift
│   ├── README.md
│   ├── oai-clang-bc.yaml
│   ├── oai-clang-is.yaml
│   ├── oai-enb-bc.yaml
│   ├── oai-enb-is.yaml
│   ├── oai-gnb-aw2s-bc.yaml
│   ├── oai-gnb-aw2s-is.yaml
│   ├── oai-gnb-bc.yaml
│   ├── oai-gnb-fhi72-bc.yaml
│   ├── oai-gnb-fhi72-is.yaml
│   ├── oai-gnb-is.yaml
│   ├── oai-lte-ue-bc.yaml
│   ├── oai-lte-ue-is.yaml
│   ├── oai-nr-cuup-bc.yaml
│   ├── oai-nr-cuup-is.yaml
│   ├── oai-nr-ue-bc.yaml
│   ├── oai-nr-ue-is.yaml
│   ├── oai-physim-bc.yaml
│   ├── oai-physim-is.yaml
│   ├── ran-base-bc.yaml
│   ├── ran-base-is.yaml
│   ├── ran-base-log-retrieval.yaml
│   ├── ran-build-bc.yaml
│   ├── ran-build-fhi72-bc.yaml
│   ├── ran-build-fhi72-is.yaml
│   └── ran-build-is.yaml
├── pre-commit-clang
├── radio
│   ├── AW2SORI
│   │   ├── CMakeLists.txt
│   │   ├── oaiori.c
│   │   └── ori.h
│   ├── BLADERF
│   │   ├── CMakeLists.txt
│   │   ├── README.md
│   │   └── bladerf_lib.c
│   ├── CMakeLists.txt
│   ├── COMMON
│   │   ├── CMakeLists.txt
│   │   ├── common_lib.c
│   │   ├── common_lib.h
│   │   ├── record_player.c
│   │   └── record_player.h
│   ├── ETHERNET
│   │   ├── CMakeLists.txt
│   │   ├── eth_raw.c
│   │   ├── eth_udp.c
│   │   ├── ethernet.md
│   │   ├── ethernet_lib.c
│   │   ├── ethernet_lib.h
│   │   └── if_defs.h
│   ├── IRIS
│   │   ├── CMakeLists.txt
│   │   └── iris_lib.cpp
│   ├── LMSSDR
│   │   ├── CMakeLists.txt
│   │   ├── LimeSDR.ini
│   │   ├── LimeSDR_above_1p8GHz.ini
│   │   ├── LimeSDR_above_1p8GHz_1v4.ini
│   │   ├── LimeSDR_below_1p8GHz.ini
│   │   ├── LimeSDR_below_1p8GHz_1v4.ini
│   │   ├── lms_lib.cpp
│   │   └── sodera_lib.cpp
│   ├── USRP
│   │   ├── CMakeLists.txt
│   │   ├── README.md
│   │   └── usrp_lib.cpp
│   ├── emulator
│   │   ├── CMakeLists.txt
│   │   ├── README.md
│   │   └── rf_emulator.c
│   ├── fhi_72
│   │   ├── CMakeLists.txt
│   │   ├── README.md
│   │   ├── armral_bfp_compression.c
│   │   ├── armral_bfp_compression.h
│   │   ├── mplane
│   │   │   ├── CMakeLists.txt
│   │   │   ├── config-mplane.c
│   │   │   ├── config-mplane.h
│   │   │   ├── connect-mplane.c
│   │   │   ├── connect-mplane.h
│   │   │   ├── get-mplane.c
│   │   │   ├── get-mplane.h
│   │   │   ├── init-mplane.c
│   │   │   ├── init-mplane.h
│   │   │   ├── rpc-send-recv.c
│   │   │   ├── rpc-send-recv.h
│   │   │   ├── ru-mplane-api.c
│   │   │   ├── ru-mplane-api.h
│   │   │   ├── subscribe-mplane.c
│   │   │   ├── subscribe-mplane.h
│   │   │   ├── xml
│   │   │   │   ├── get-xml.c
│   │   │   │   └── get-xml.h
│   │   │   └── yang
│   │   │       ├── create-yang-config.c
│   │   │       ├── create-yang-config.h
│   │   │       ├── get-yang.c
│   │   │       ├── get-yang.h
│   │   │       └── models
│   │   │           ├── iana-hardware.yang
│   │   │           ├── iana-if-type.yang
│   │   │           ├── ietf-crypto-types.yang
│   │   │           ├── ietf-hardware.yang
│   │   │           ├── ietf-interfaces.yang
│   │   │           ├── ietf-ip.yang
│   │   │           ├── ietf-netconf-acm.yang
│   │   │           ├── o-ran-common-yang-types.yang
│   │   │           ├── o-ran-compression-factors.yang
│   │   │           ├── o-ran-delay-management.yang
│   │   │           ├── o-ran-file-management.yang
│   │   │           ├── o-ran-hardware.yang
│   │   │           ├── o-ran-interfaces.yang
│   │   │           ├── o-ran-module-cap.yang
│   │   │           ├── o-ran-performance-management.yang
│   │   │           ├── o-ran-processing-element.yang
│   │   │           ├── o-ran-uplane-conf.yang
│   │   │           ├── o-ran-usermgmt.yang
│   │   │           └── o-ran-wg4-features.yang
│   │   ├── oaioran.c
│   │   ├── oaioran.h
│   │   ├── oran-config.c
│   │   ├── oran-config.h
│   │   ├── oran-init.c
│   │   ├── oran-init.h
│   │   ├── oran-params.h
│   │   ├── oran.h
│   │   ├── oran_isolate.c
│   │   └── oran_isolate.h
│   ├── iqplayer
│   │   ├── DOC
│   │   │   └── iqrecordplayer_usage.md
│   │   └── iqplayer_lib.c
│   ├── rfsimulator
│   │   ├── CMakeLists.txt
│   │   ├── README.md
│   │   ├── apply_channelmod.c
│   │   ├── rfsimulator.h
│   │   ├── simulator.cpp
│   │   └── stored_node.c
│   ├── vrtsim
│   │   ├── CMakeLists.txt
│   │   ├── README.md
│   │   ├── cirdb_provider.c
│   │   ├── cirdb_provider.h
│   │   ├── cirdb_yaml.cpp
│   │   ├── cirdb_yaml.h
│   │   ├── taps_client.cpp
│   │   ├── taps_client.h
│   │   ├── tests
│   │   │   ├── CMakeLists.txt
│   │   │   ├── test_vrtsim.cpp
│   │   │   ├── test_vrtsim_cirdb.cpp
│   │   │   └── test_vrtsim_taps.cpp
│   │   └── vrtsim.c
│   └── zmq
│       ├── CMakeLists.txt
│       ├── README.md
│       ├── ring_buffer.cpp
│       ├── ring_buffer.h
│       ├── tests
│       │   ├── CMakeLists.txt
│       │   ├── test_ring_buffer.cpp
│       │   └── test_zmq_radio.cpp
│       ├── zmq_imported.cpp
│       ├── zmq_imported.h
│       └── zmq_radio.cpp
├── targets
│   ├── DOCS
│   │   ├── E-UTRAN_User_Guide.docx
│   │   ├── E-UTRAN_User_Guide.pdf
│   │   ├── nfapi-L2-emulator-setup.txt
│   │   ├── oai_L1_L2_procedures.ipe
│   │   └── oai_L1_L2_procedures.pdf
│   ├── PROJECTS
│   │   ├── CENTOS-LTE-EPC-INTEGRATION
│   │   │   └── CONF
│   │   │       ├── enb.centos.calisson.conf
│   │   │       ├── enb.centos.memphis.conf
│   │   │       └── enb.centos.nord.conf
│   │   ├── GENERIC-LTE-EPC
│   │   │   └── CONF
│   │   │       ├── UE_config.xml
│   │   │       ├── benetel-4g.conf
│   │   │       ├── benetel-5g.conf
│   │   │       ├── enb.band13.tm1.50PRB.emtc.conf
│   │   │       ├── enb.band38.tm1.100PRB.usrpx310.conf
│   │   │       ├── enb.band38.tm1.25PRB.iris030.conf
│   │   │       ├── enb.band38.tm1.usrpx310.conf
│   │   │       ├── enb.band42.tm1.25PRB.iris030.conf
│   │   │       ├── enb.band7.25prb.bladerf.conf
│   │   │       ├── enb.band7.master.conf
│   │   │       ├── enb.band7.tm1.100PRB.usrpx310.conf
│   │   │       ├── enb.band7.tm1.25PRB.iris030.conf
│   │   │       ├── enb.band7.tm1.25PRB.usrpb210.replay.conf
│   │   │       ├── enb.band7.tm1.50PRB.usrpb210-d2d.conf
│   │   │       ├── enb.band7.tm1.50PRB.usrpb210.conf
│   │   │       ├── enb.band7.tm1.50PRB.usrpb210_ue_expansion.conf
│   │   │       ├── gnb.band257.tm1.32PRB.usrpn300.conf
│   │   │       ├── gnb.band257.tm1.32PRB.usrpx300.conf
│   │   │       ├── gnb.band257.tm1.66PRB.usrpn300.conf
│   │   │       ├── gnb.band261.tm1.32PRB.usrpn300.conf
│   │   │       ├── gnb.band66.tm1.106PRB.usrpn300.conf
│   │   │       ├── gnb.band66.tm1.106PRB.usrpx300.conf
│   │   │       ├── gnb.band66.tm1.24PRB.usrpx300.conf
│   │   │       ├── gnb.band66.tm1.25PRB.usrpn300.conf
│   │   │       ├── gnb.band66.tm1.25PRB.usrpx300.conf
│   │   │       ├── gnb.band78.106PRB.30kHz,usrpb2x0.conf
│   │   │       ├── gnb.band78.106PRB.slave.conf
│   │   │       ├── gnb.band78.slave.conf
│   │   │       ├── gnb.band78.tm1.106PRB.PTRS.usrpx300.conf
│   │   │       ├── gnb.band78.tm1.106PRB.usrpb210.conf
│   │   │       ├── gnb.band78.tm1.106PRB.usrpn300.conf
│   │   │       ├── gnb.band78.tm1.106PRB.usrpx300.conf
│   │   │       ├── gnb.band78.tm1.217PRB.usrpn300.conf
│   │   │       ├── gnb.band78.tm1.217PRB.usrpx300.conf
│   │   │       ├── gnb.band78.tm1.24PRB.usrpb210.conf
│   │   │       ├── gnb.band78.tm1.24PRB.usrpn300.conf
│   │   │       ├── gnb.band78.tm1.24PRB.usrpx300.conf
│   │   │       ├── gnb.band78.tm1.273PRB.usrpn300.conf
│   │   │       ├── oaiL1.nfapi.usrpx300.conf
│   │   │       ├── rcc.band38.tm1.if4p5.50PRB.lo.conf
│   │   │       ├── rcc.band7.tm1.50PRB.nfapi-STUB.conf
│   │   │       ├── rcc.band7.tm1.50PRB.nfapi.conf
│   │   │       ├── rcc.band7.tm1.if4p5.50PRB.conf
│   │   │       ├── rcc.band7.tm1.if4p5.50PRB.lo.conf
│   │   │       ├── rcc_b38_if5_ENDC.conf
│   │   │       ├── rru.oaisim.conf
│   │   │       └── rru.oaisim.tdd.conf
│   │   ├── GENERIC-NR-5GC
│   │   │   └── CONF
│   │   │       ├── channelmod_rfsimu.conf
│   │   │       ├── channelmod_rfsimu_LEO_satellite.conf
│   │   │       ├── cu_gnb.conf
│   │   │       ├── du_gnb.conf
│   │   │       ├── gnb-cu.sa.f1.conf
│   │   │       ├── gnb-du.sa.band66.25prb.rfsim.pci0.conf
│   │   │       ├── gnb-du.sa.band66.25prb.rfsim.pci1.conf
│   │   │       ├── gnb-du.sa.band77.273prb.fhi72.4x4-benetel650.conf
│   │   │       ├── gnb-du.sa.band77.273prb.fhi72.4x4-das-benetel650_650.conf
│   │   │       ├── gnb-du.sa.band77.273prb.fhi72.8x8-benetel650_650-mplane.conf
│   │   │       ├── gnb-du.sa.band77.273prb.fhi72.8x8-benetel650_650.conf
│   │   │       ├── gnb-du.sa.band78.106prb.rfsim.pci0.conf
│   │   │       ├── gnb-du.sa.band78.106prb.rfsim.pci1.conf
│   │   │       ├── gnb-pnf.band78.rfsim.2x2.conf
│   │   │       ├── gnb-pnf.band78.rfsim.conf
│   │   │       ├── gnb-vnf.sa.band78.106prb.nfapi.conf
│   │   │       ├── gnb-vnf.sa.band78.273prb.aerial.conf
│   │   │       ├── gnb-vnf.sa.band78.273prb.nfapi.conf
│   │   │       ├── gnb-vnf.sa.cbrs.aerial.conf
│   │   │       ├── gnb.band78.sa.fr1.106PRB.2x2.usrpn310.conf
│   │   │       ├── gnb.band78.sa.fr1.162PRB.2x2.usrpn310.conf
│   │   │       ├── gnb.sa.band1.u0.52PRB.usrpb210.conf
│   │   │       ├── gnb.sa.band254.ntn.mu1.24prb.rfsim.conf
│   │   │       ├── gnb.sa.band255.ntn.mu0.25prb.rfsim.conf
│   │   │       ├── gnb.sa.band256.ntn.mu0.25prb.rfsim.conf
│   │   │       ├── gnb.sa.band257.132prb.fhi72.2x2-liteon.conf
│   │   │       ├── gnb.sa.band257.132prb.fhi72.2x2-microamp.conf
│   │   │       ├── gnb.sa.band257.u3.32prb.usrpx410.conf
│   │   │       ├── gnb.sa.band41.fr1.106PRB.usrpb210.conf
│   │   │       ├── gnb.sa.band41.fr1.52PRB.usrpb210.conf
│   │   │       ├── gnb.sa.band512.ntn.mu3.132prb.rfsim.conf
│   │   │       ├── gnb.sa.band512.ntn.mu3.32prb.rfsim.conf
│   │   │       ├── gnb.sa.band512.ntn.mu3.66prb.rfsim.conf
│   │   │       ├── gnb.sa.band66.fr1.106PRB.usrpn300.conf
│   │   │       ├── gnb.sa.band66.fr1.106PRB.usrpx300.conf
│   │   │       ├── gnb.sa.band66.fr1.24PRB.usrpx300.conf
│   │   │       ├── gnb.sa.band66.fr1.25PRB.usrpx300.conf
│   │   │       ├── gnb.sa.band66.u0.25prb.rfsim.conf
│   │   │       ├── gnb.sa.band77.106prb.fhi72.4x4-vvdn.conf
│   │   │       ├── gnb.sa.band77.162prb.usrpn310.4x4.conf
│   │   │       ├── gnb.sa.band77.273prb.fhi72.2x2-benetel550-long-prach.conf
│   │   │       ├── gnb.sa.band77.273prb.fhi72.2x2-vvdn-16b.conf
│   │   │       ├── gnb.sa.band77.273prb.fhi72.4x4-vvdn.conf
│   │   │       ├── gnb.sa.band77.273prb.fhi72.4x4-wnc.conf
│   │   │       ├── gnb.sa.band77.fr1.273PRB.2x2.usrpn300.conf
│   │   │       ├── gnb.sa.band77.fr1.273PRB.usrpx300.conf
│   │   │       ├── gnb.sa.band78.106PRB.usrpb210.RA_2-Step.conf
│   │   │       ├── gnb.sa.band78.106prb.bladerf2.0xa4.conf
│   │   │       ├── gnb.sa.band78.106prb.fhi72.1x1-proto-ru.conf
│   │   │       ├── gnb.sa.band78.273prb.fhi72.2x2-benetel550-16b.conf
│   │   │       ├── gnb.sa.band78.273prb.fhi72.4x2-benetel550.conf
│   │   │       ├── gnb.sa.band78.273prb.fhi72.4x4-benetel550-mplane.conf
│   │   │       ├── gnb.sa.band78.273prb.fhi72.4x4-benetel550.conf
│   │   │       ├── gnb.sa.band78.273prb.fhi72.4x4-foxconn.conf
│   │   │       ├── gnb.sa.band78.273prb.fhi72.4x4-liteon.conf
│   │   │       ├── gnb.sa.band78.273prb.fhi72.4x4-metanoia.conf
│   │   │       ├── gnb.sa.band78.51PRB.bladerf2.0xa4.conf
│   │   │       ├── gnb.sa.band78.fr1.106PRB.2x2.usrpn300.conf
│   │   │       ├── gnb.sa.band78.fr1.106PRB.pci0.rfsim.conf
│   │   │       ├── gnb.sa.band78.fr1.106PRB.pci1.rfsim.conf
│   │   │       ├── gnb.sa.band78.fr1.106PRB.usrpb210.2pattern.conf
│   │   │       ├── gnb.sa.band78.fr1.106PRB.usrpb210.4layer.conf
│   │   │       ├── gnb.sa.band78.fr1.106PRB.usrpb210.conf
│   │   │       ├── gnb.sa.band78.fr1.106PRB.usrpb210.redcap.yaml
│   │   │       ├── gnb.sa.band78.fr1.106PRB.usrpb210.sabox.conf
│   │   │       ├── gnb.sa.band78.fr1.106PRB.usrpb210.yaml
│   │   │       ├── gnb.sa.band78.fr1.162PRB.2x2.usrpn300.conf
│   │   │       ├── gnb.sa.band78.fr1.189PRB.rfsim.conf
│   │   │       ├── gnb.sa.band78.fr1.217PRB.2x2.usrpn300.conf
│   │   │       ├── gnb.sa.band78.fr1.24PRB.usrpb210.conf
│   │   │       ├── gnb0.prs.band261.fr2.64PRB.usrpx310.conf
│   │   │       ├── gnb0.prs.band78.fr1.106PRB.usrpx310.conf
│   │   │       ├── gnb1.prs.band261.fr2.64PRB.usrpx310.conf
│   │   │       ├── gnb1.prs.band78.fr1.106PRB.usrpx310.conf
│   │   │       ├── neighbour-config-rfsim.conf
│   │   │       ├── ue.conf
│   │   │       ├── ue.nr.prs.fr1.106prb.conf
│   │   │       ├── ue.nr.prs.fr2.64prb.conf
│   │   │       ├── uecap_ports1.xml
│   │   │       ├── uecap_ports2.xml
│   │   │       └── uecap_ports4.xml
│   │   └── NR-SIDELINK
│   │       └── CONF
│   │           ├── sidelink_preconfig_1rxpool.conf
│   │           ├── sidelink_preconfig_1rxpool_1txpool.conf
│   │           └── sidelink_preconfig_1txpool.conf
│   ├── TEST
│   │   ├── AT_COMMANDS
│   │   │   ├── Makefile
│   │   │   └── oaisim.c
│   │   ├── PDCP
│   │   │   ├── Makefile
│   │   │   ├── readme.txt
│   │   │   ├── test_pdcp.c
│   │   │   ├── test_pdcp.h
│   │   │   ├── test_util.h
│   │   │   ├── todo.txt
│   │   │   └── with_rlc
│   │   │       ├── Makefile.data_bearer
│   │   │       ├── readme_test_pdcp_rlc.txt
│   │   │       └── test_pdcp_rlc.c
│   │   └── ROHDE_SCHWARZ
│   │       ├── EthernetRawCommand.cpp
│   │       ├── Makefile
│   │       ├── TcpClient.cpp
│   │       └── TcpClient.h
│   └── gtkwave
│       ├── eNB_usrp.gtkw
│       ├── gNB_usrp.gtkw
│       ├── pnf.gtkw
│       ├── rau_if4_single_thread.gtkw
│       ├── rcc_if4.gtkw
│       ├── rcc_if5.gtkw
│       ├── rru_if4p5_simulator.gtkw
│       ├── rru_if4p5_single_thread.gtkw
│       ├── rru_if4p5_usrp.gtkw
│       ├── rru_if5_usrp.gtkw
│       └── ue_usrp.gtkw
├── tests
│   ├── CMakeLists.txt
│   ├── nr-cu-nrppa
│   │   ├── CMakeLists.txt
│   │   ├── README.md
│   │   ├── nr-cu-nrppa.c
│   │   └── nr-nrppa-test.conf
│   ├── nr-cuup
│   │   ├── CMakeLists.txt
│   │   ├── README.md
│   │   ├── load-test.conf
│   │   ├── nr-cuup-functional-test.sh
│   │   └── nr-cuup-load-test.c
│   └── nr-ue-nas-simulator
│       ├── CMakeLists.txt
│       ├── README.md
│       ├── nr-ue-nas-simulator.c
│       └── test.conf
└── tools
    ├── cppcheck
    │   ├── README.md
    │   ├── docker-compose.yaml
    │   ├── run-cppcheck.sh
    │   └── suppressions.list
    ├── docker-dev-env
    │   ├── Dockerfile
    │   ├── README.md
    │   ├── bootstrap.sh
    │   └── docker-compose.yml
    ├── formatting
    │   ├── README.md
    │   ├── detect_clang_format_errors.sh
    │   └── docker-compose.yaml
    ├── iwyu
    │   ├── README.md
    │   └── docker-compose.yaml
    ├── packages
    │   ├── packages.cmake
    │   ├── systemd_scripts
    │   │   ├── oai-lte
    │   │   │   ├── postinst
    │   │   │   └── prerm
    │   │   ├── oai-nr
    │   │   │   ├── postinst
    │   │   │   └── prerm
    │   │   ├── postinst
    │   │   └── prerm
    │   ├── systemd_services
    │   │   ├── oai-lte
    │   │   │   └── lte-softmodem.service
    │   │   └── oai-nr
    │   │       ├── nr-cuup.service
    │   │       └── nr-softmodem.service
    │   └── triggers
    ├── plots
    │   ├── README.md
    │   ├── ber_compare.svg
    │   ├── dl_graph.py
    │   ├── example.png
    │   ├── plot-power-control.gp.sh
    │   ├── requirements.txt
    │   └── ul_bler_vs_snr_graph.py
    └── scripts
        └── multi-ue.sh
```
552 directories, 4197 files
