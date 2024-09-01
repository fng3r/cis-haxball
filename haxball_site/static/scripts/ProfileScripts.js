
    let ProfileTabs = document.querySelectorAll('.profile-tabs');
    let firstTab = ProfileTabs[0];
    let secondTab = ProfileTabs[1];

    firstTab.addEventListener("click", function(event){
        document.getElementById('profile-info-tab').style.color = '#000000';
        document.getElementById('profile-achievements-tab').style.color = '#007bff';
    });


    secondTab.addEventListener("click",function(event){
        document.getElementById('profile-achievements-tab').style.color = '#000000';
        document.getElementById('profile-info-tab').style.color = '#007bff';
    });


    let nicknamesHistoryButton = document.querySelector('.nickname-inline');
    let isHistoryHidden = true;

    nicknamesHistoryButton.addEventListener("click",function(event){
        if(isHistoryHidden){
            document.querySelector('.nicknames-history').style.opacity = '0.85';
            document.querySelector('.nicknames-history').style.visibility = 'visible';
            document.querySelector('.profile-triangle').style.transform = 'rotate(180deg)';
            isHistoryHidden = false;
        } else {
            document.querySelector('.nicknames-history').style.opacity = '0';
            document.querySelector('.nicknames-history').style.visibility = 'hidden';
            document.querySelector('.profile-triangle').style.transform = 'rotate(0deg)';
            isHistoryHidden = true;
        }
    });